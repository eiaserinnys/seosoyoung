"""commands.py 단위 테스트

분리된 명령어 핸들러들과 유틸리티 함수, 디스패치 라우터를 테스트합니다.
"""

import pytest
from unittest.mock import MagicMock, patch

from seosoyoung.slackbot.handlers.commands import (
    get_ancestors,
    format_elapsed,
    handle_help,
    handle_status,
    handle_cleanup,
    handle_log,
    handle_translate,
    handle_update_restart,
    handle_compact,
    handle_profile,
    handle_resume_list_run,
)
from seosoyoung.slackbot.handlers.mention import (
    try_handle_command,
    _is_admin_command,
    _COMMAND_DISPATCH,
)


# ── 유틸리티 함수 테스트 ──────────────────────────────────────


class TestFormatElapsed:
    def test_seconds(self):
        assert format_elapsed(30) == "30초"

    def test_minutes(self):
        assert format_elapsed(120) == "2분"

    def test_hours(self):
        assert format_elapsed(7200) == "2시간"

    def test_boundary_60(self):
        assert format_elapsed(60) == "1분"

    def test_boundary_3600(self):
        assert format_elapsed(3600) == "1시간"


class TestGetAncestors:
    @patch("seosoyoung.slackbot.handlers.commands.psutil")
    def test_returns_ancestor_chain(self, mock_psutil):
        """조상 체인을 올바르게 반환하는지 확인"""
        proc1 = MagicMock()
        proc1.ppid.return_value = 100

        proc2 = MagicMock()
        proc2.ppid.return_value = 0

        mock_psutil.Process.side_effect = [proc1, proc2]

        result = get_ancestors(200)
        assert result == [100]

    @patch("seosoyoung.slackbot.handlers.commands.psutil")
    def test_handles_no_such_process(self, mock_psutil):
        """프로세스가 없는 경우 빈 리스트 반환"""
        import psutil
        mock_psutil.NoSuchProcess = psutil.NoSuchProcess
        mock_psutil.AccessDenied = psutil.AccessDenied
        mock_psutil.ZombieProcess = psutil.ZombieProcess
        mock_psutil.Process.side_effect = psutil.NoSuchProcess(999)

        result = get_ancestors(999)
        assert result == []


# ── _is_admin_command 테스트 ──────────────────────────────────


class TestIsAdminCommand:
    def test_exact_matches(self):
        for cmd in ["help", "status", "update", "restart", "compact", "profile", "cleanup", "log"]:
            assert _is_admin_command(cmd), f"{cmd} should be admin command"

    def test_profile_subcommands(self):
        assert _is_admin_command("profile list")
        assert _is_admin_command("profile save work")

    def test_cleanup_confirm(self):
        assert _is_admin_command("cleanup confirm")

    def test_non_admin(self):
        assert not _is_admin_command("hello")
        assert not _is_admin_command("번역 hello")


# ── 디스패치 라우터 테스트 ──────────────────────────────────────


def _make_deps(**overrides):
    """테스트용 deps 딕셔너리 생성"""
    deps = {
        "session_manager": MagicMock(),
        "restart_manager": MagicMock(is_pending=False),
        "check_permission": MagicMock(return_value=True),
        "get_running_session_count": MagicMock(return_value=0),
        "send_restart_confirmation": MagicMock(),
        "list_runner_ref": MagicMock(return_value=None),
    }
    deps.update(overrides)
    return deps


class TestTryHandleCommandDispatch:
    """try_handle_command 디스패치 라우터 테스트"""

    def test_help_dispatched(self):
        say = MagicMock()
        deps = _make_deps()
        result = try_handle_command("help", "", "C1", "ts1", None, "U1", say, MagicMock(), deps)
        assert result is True
        assert say.called
        assert "사용법" in say.call_args[1]["text"]

    def test_unknown_command_returns_false(self):
        say = MagicMock()
        deps = _make_deps()
        result = try_handle_command("unknown", "", "C1", "ts1", None, "U1", say, MagicMock(), deps)
        assert result is False
        assert not say.called

    def test_restart_pending_blocks_non_admin(self):
        say = MagicMock()
        deps = _make_deps(restart_manager=MagicMock(is_pending=True))
        result = try_handle_command("hello", "", "C1", "ts1", None, "U1", say, MagicMock(), deps)
        assert result is True
        assert "재시작" in say.call_args[1]["text"]

    def test_restart_pending_allows_admin(self):
        """재시작 대기 중에도 help 명령어는 정상 처리"""
        say = MagicMock()
        deps = _make_deps(restart_manager=MagicMock(is_pending=True))
        result = try_handle_command("help", "", "C1", "ts1", None, "U1", say, MagicMock(), deps)
        assert result is True
        assert "사용법" in say.call_args[1]["text"]

    def test_translate_prefix_match(self):
        """'번역 ' 프리픽스 매치"""
        say = MagicMock()
        client = MagicMock()
        deps = _make_deps()
        with patch("seosoyoung.slackbot.translator.detect_language") as mock_detect, \
             patch("seosoyoung.slackbot.translator.translate") as mock_translate:
            mock_detect.return_value = MagicMock(value="ko")
            mock_translate.return_value = ("Hello", 0.001, [], None)
            result = try_handle_command(
                "번역 안녕", "번역 안녕", "C1", "ts1", None, "U1", say, client, deps
            )
        assert result is True

    def test_profile_prefix_match(self):
        """'profile' 프리픽스 매치"""
        say = MagicMock()
        deps = _make_deps()
        with patch("seosoyoung.slackbot.handlers.commands._handle_profile_list"):
            result = try_handle_command(
                "profile list", "", "C1", "ts1", None, "U1", say, MagicMock(), deps
            )
        assert result is True

    def test_dispatch_table_contains_expected_commands(self):
        """디스패치 테이블에 예상된 명령어가 모두 있는지 확인"""
        expected = {"help", "status", "cleanup", "cleanup confirm", "log", "update", "restart", "compact"}
        assert set(_COMMAND_DISPATCH.keys()) == expected


# ── 개별 핸들러 테스트 ──────────────────────────────────────────


class TestHandleHelp:
    def test_returns_help_text(self):
        say = MagicMock()
        handle_help(say=say, ts="ts1")
        say.assert_called_once()
        text = say.call_args[1]["text"]
        assert "사용법" in text
        assert "help" in text
        assert "status" in text
        assert "compact" in text


class TestHandleLog:
    def test_permission_denied(self):
        say = MagicMock()
        handle_log(
            say=say, ts="ts1", thread_ts=None, channel="C1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands.Path")
    def test_no_log_files(self, mock_path):
        say = MagicMock()
        mock_log_dir = MagicMock()
        mock_path.return_value = mock_log_dir
        # log files don't exist
        log_file = MagicMock()
        log_file.exists.return_value = False
        mock_log_dir.__truediv__ = MagicMock(return_value=log_file)

        handle_log(
            say=say, ts="ts1", thread_ts=None, channel="C1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert any("로그 파일이 없습니다" in str(c) for c in say.call_args_list)


class TestHandleUpdateRestart:
    def test_permission_denied(self):
        say = MagicMock()
        handle_update_restart(
            command="restart", say=say, ts="ts1", user_id="U1",
            client=MagicMock(),
            restart_manager=MagicMock(),
            check_permission=MagicMock(return_value=False),
            get_running_session_count=MagicMock(return_value=0),
            send_restart_confirmation=MagicMock(),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    def test_restart_with_running_sessions(self):
        send_confirm = MagicMock()
        handle_update_restart(
            command="restart", say=MagicMock(), ts="ts1", user_id="U1",
            client=MagicMock(),
            restart_manager=MagicMock(),
            check_permission=MagicMock(return_value=True),
            get_running_session_count=MagicMock(return_value=2),
            send_restart_confirmation=send_confirm,
        )
        send_confirm.assert_called_once()

    def test_restart_no_running_sessions(self):
        restart_mgr = MagicMock()
        handle_update_restart(
            command="restart", say=MagicMock(), ts="ts1", user_id="U1",
            client=MagicMock(),
            restart_manager=restart_mgr,
            check_permission=MagicMock(return_value=True),
            get_running_session_count=MagicMock(return_value=0),
            send_restart_confirmation=MagicMock(),
        )
        restart_mgr.force_restart.assert_called_once()


class TestHandleCompact:
    def test_shows_auto_message(self):
        say = MagicMock()
        handle_compact(say=say, ts="ts1", thread_ts=None)
        assert "Soulstream" in say.call_args[1]["text"]

    def test_shows_auto_message_in_thread(self):
        say = MagicMock()
        handle_compact(say=say, ts="ts1", thread_ts="thread1")
        assert "Soulstream" in say.call_args[1]["text"]
        assert say.call_args[1]["thread_ts"] == "thread1"


class TestHandleProfile:
    def test_permission_denied(self):
        say = MagicMock()
        handle_profile(
            command="profile list", say=say, thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    def test_shows_usage_on_unknown_subcmd(self):
        say = MagicMock()
        handle_profile(
            command="profile unknown", say=say, thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "사용법" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._handle_profile_list")
    def test_bare_profile_shows_list(self, mock_list):
        """인자 없는 profile은 목록 표시"""
        say = MagicMock()
        handle_profile(
            command="profile", say=say, thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_list.assert_called_once_with(say, None)

    @patch("seosoyoung.slackbot.handlers.commands._handle_profile_list")
    def test_profile_list_shows_list(self, mock_list):
        """profile list도 목록 표시"""
        say = MagicMock()
        handle_profile(
            command="profile list", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_list.assert_called_once_with(say, "ts1")

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_profile_api")
    def test_profile_save(self, mock_api):
        """profile save → Soul API 호출"""
        say = MagicMock()
        handle_profile(
            command="profile save work", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_api.assert_called_once()
        assert "저장" in say.call_args[1]["text"]
        assert "work" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_profile_api")
    def test_profile_delete(self, mock_api):
        """profile delete → Soul API 호출"""
        say = MagicMock()
        handle_profile(
            command="profile delete old", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_api.assert_called_once()
        assert "삭제" in say.call_args[1]["text"]
        assert "old" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_profile_api")
    def test_profile_change(self, mock_api):
        """profile change → Soul API activate 호출"""
        say = MagicMock()
        handle_profile(
            command="profile change personal", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_api.assert_called_once()
        assert "전환" in say.call_args[1]["text"]
        assert "personal" in say.call_args[1]["text"]

    def test_profile_save_no_arg(self):
        """profile save 인자 없으면 안내 메시지"""
        say = MagicMock()
        handle_profile(
            command="profile save", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "이름을 입력" in say.call_args[1]["text"]

    def test_profile_delete_no_arg(self):
        """profile delete 인자 없으면 안내 메시지"""
        say = MagicMock()
        handle_profile(
            command="profile delete", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "이름을 입력" in say.call_args[1]["text"]

    def test_profile_change_no_arg(self):
        """profile change 인자 없으면 안내 메시지"""
        say = MagicMock()
        handle_profile(
            command="profile change", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "이름을 입력" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_profile_api")
    def test_soul_service_error_handled(self, mock_api):
        """SoulServiceError 발생 시 에러 메시지 표시"""
        from seosoyoung.slackbot.claude.service_client import SoulServiceError
        mock_api.side_effect = SoulServiceError("프로필을 찾을 수 없습니다: bad")
        say = MagicMock()
        handle_profile(
            command="profile delete bad", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "❌" in say.call_args[1]["text"]
        assert "프로필을 찾을 수 없습니다" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_profile_api")
    def test_generic_exception_handled(self, mock_api):
        """예상치 못한 예외 시 에러 메시지 표시"""
        mock_api.side_effect = ConnectionError("network down")
        say = MagicMock()
        handle_profile(
            command="profile save test", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "오류가 발생했습니다" in say.call_args[1]["text"]

    def test_invalid_profile_name_rejected(self):
        """유효하지 않은 프로필 이름은 API 호출 없이 거부"""
        say = MagicMock()
        handle_profile(
            command="profile save ../etc/passwd", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "영문/숫자" in say.call_args[1]["text"]

    def test_special_chars_in_name_rejected(self):
        """특수문자 포함 프로필 이름 거부 (단일 토큰으로 파싱되는 이름)"""
        say = MagicMock()
        # command.split()으로 파싱되므로 공백 포함 이름은 테스트하지 않음
        for name in [".hidden", "_reserved", "한글이름"]:
            handle_profile(
                command=f"profile save {name}", say=say, thread_ts="ts1",
                client=MagicMock(), user_id="U1",
                check_permission=MagicMock(return_value=True),
            )
            assert "영문/숫자" in say.call_args[1]["text"], f"Should reject '{name}'"


class TestHandleResumeListRun:
    def test_no_list_runner(self):
        say = MagicMock()
        handle_resume_list_run(say=say, ts="ts1", list_runner_ref=None)
        assert "초기화되지 않았습니다" in say.call_args[1]["text"]

    def test_no_paused_sessions(self):
        say = MagicMock()
        runner = MagicMock()
        runner.get_paused_sessions.return_value = []
        handle_resume_list_run(say=say, ts="ts1", list_runner_ref=lambda: runner)
        assert "중단된 정주행 세션이 없습니다" in say.call_args[1]["text"]

    def test_resume_success(self):
        say = MagicMock()
        session = MagicMock()
        session.session_id = "sess-1"
        session.list_name = "Test List"
        session.current_index = 2
        session.card_ids = ["a", "b", "c"]

        runner = MagicMock()
        runner.get_paused_sessions.return_value = [session]
        runner.resume_run.return_value = True

        handle_resume_list_run(say=say, ts="ts1", list_runner_ref=lambda: runner)
        assert "정주행 재개" in say.call_args[1]["text"]
        runner.resume_run.assert_called_once_with("sess-1")


class TestHandleCleanup:
    def test_permission_denied(self):
        say = MagicMock()
        handle_cleanup(
            command="cleanup", say=say, ts="ts1", client=MagicMock(),
            user_id="U1", session_manager=MagicMock(),
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]
