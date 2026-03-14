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
    handle_session_info,
    handle_set_token,
    handle_clear_token,
    _sanitize_email_to_profile_name,
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
        for cmd in ["help", "status", "update", "restart", "compact", "profile", "cleanup", "log", "session-info", "clear-token"]:
            assert _is_admin_command(cmd), f"{cmd} should be admin command"

    def test_profile_subcommands(self):
        assert _is_admin_command("profile list")
        assert _is_admin_command("profile save work")

    def test_cleanup_confirm(self):
        assert _is_admin_command("cleanup confirm")

    def test_set_token_subcommand(self):
        assert _is_admin_command("set-token sk-ant-oat01-xxx")

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
        mock_plugin = MagicMock()
        mock_plugin.translate_text.return_value = ("Hello", 0.001, [], MagicMock(value="ko"))
        mock_pm = MagicMock()
        mock_pm.plugins = {"translate": mock_plugin}
        deps = _make_deps(plugin_manager=mock_pm)
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
        expected = {
            "help", "status", "cleanup", "cleanup confirm", "log",
            "update", "restart", "compact", "plugins", "session-info",
            "clear-token",
        }
        assert set(_COMMAND_DISPATCH.keys()) == expected

    def test_set_token_prefix_match(self):
        """'set-token' 프리픽스 매치"""
        say = MagicMock()
        deps = _make_deps()
        with patch("seosoyoung.slackbot.handlers.commands._run_soul_api") as mock_api:
            mock_api.return_value = {"success": True}
            result = try_handle_command(
                "set-token sk-ant-oat01-xxx", "", "C1", "ts1", None, "U1", say, MagicMock(), deps
            )
        assert result is True

    def test_clear_token_dispatched(self):
        """'clear-token' 디스패치"""
        say = MagicMock()
        deps = _make_deps()
        with patch("seosoyoung.slackbot.handlers.commands._run_soul_api") as mock_api:
            mock_api.return_value = {"success": True, "message": "삭제됨"}
            result = try_handle_command(
                "clear-token", "", "C1", "ts1", None, "U1", say, MagicMock(), deps
            )
        assert result is True


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
    def test_no_thread_ts_shows_guide(self):
        """스레드 밖에서 호출 시 안내 메시지"""
        say = MagicMock()
        handle_compact(
            say=say, ts="ts1", thread_ts=None,
            channel="C1", client=MagicMock(), session_manager=MagicMock(),
        )
        assert "스레드에서 사용" in say.call_args[1]["text"]

    def test_no_session_shows_guide(self):
        """활성 세션이 없을 때 안내 메시지"""
        say = MagicMock()
        sm = MagicMock()
        sm.get.return_value = None
        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=MagicMock(), session_manager=sm,
        )
        assert "활성 세션" in say.call_args[1]["text"]

    def test_no_session_id_shows_guide(self):
        """세션은 있지만 session_id가 없을 때 안내 메시지"""
        say = MagicMock()
        sm = MagicMock()
        session = MagicMock()
        session.session_id = None
        sm.get.return_value = session
        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=MagicMock(), session_manager=sm,
        )
        assert "활성 세션" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_compact_success(self, mock_compact):
        """compact 성공 시 완료 메시지로 교체"""
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "progress_ts"}
        sm = MagicMock()
        session = MagicMock()
        session.session_id = "agent-session-123"
        sm.get.return_value = session

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.agent_session_id = "agent-session-123"
        mock_compact.return_value = mock_result

        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=client, session_manager=sm,
        )

        # 진행 메시지 전송 확인
        client.chat_postMessage.assert_called_once()
        assert "진행" in client.chat_postMessage.call_args[1]["text"]

        # 완료 메시지로 업데이트 확인
        client.chat_update.assert_called_once()
        assert "완료" in client.chat_update.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_compact_failure(self, mock_compact):
        """compact 실패 시 실패 메시지로 교체"""
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "progress_ts"}
        sm = MagicMock()
        session = MagicMock()
        session.session_id = "agent-session-123"
        sm.get.return_value = session

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "세션을 찾을 수 없습니다"
        mock_compact.return_value = mock_result

        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=client, session_manager=sm,
        )

        client.chat_update.assert_called_once()
        assert "실패" in client.chat_update.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_compact_exception(self, mock_compact):
        """compact 중 예외 발생 시 오류 메시지로 교체"""
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "progress_ts"}
        sm = MagicMock()
        session = MagicMock()
        session.session_id = "agent-session-123"
        sm.get.return_value = session

        mock_compact.side_effect = RuntimeError("connection refused")

        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=client, session_manager=sm,
        )

        client.chat_update.assert_called_once()
        assert "오류" in client.chat_update.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_compact_updates_session_id(self, mock_compact):
        """compact 후 세션 ID 업데이트 확인"""
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "progress_ts"}
        sm = MagicMock()
        session = MagicMock()
        session.session_id = "old-session-id"
        sm.get.return_value = session

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.agent_session_id = "new-session-id"
        mock_compact.return_value = mock_result

        handle_compact(
            say=say, ts="ts1", thread_ts="thread1",
            channel="C1", client=client, session_manager=sm,
        )

        sm.update_session_id.assert_called_once_with("thread1", "new-session-id")

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_compact_success_no_new_session_id(self, mock_api):
        """compact 성공이지만 session_id 변경 없을 때 update_session_id 미호출"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "progress_ts"}
        sm = MagicMock()
        session = MagicMock()
        session.session_id = "agent-session-123"
        sm.get.return_value = session

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.agent_session_id = None
        mock_api.return_value = mock_result

        handle_compact(
            say=MagicMock(), ts="ts1", thread_ts="thread1",
            channel="C1", client=client, session_manager=sm,
        )

        sm.update_session_id.assert_not_called()
        assert "완료" in client.chat_update.call_args[1]["text"]


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

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
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

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
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

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
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

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_profile_save_no_arg_email_found(self, mock_api):
        """profile save (인자 없음) + 이메일 찾음 → 자동 저장"""
        # 첫 호출: get_current_email → "user@example.com"
        # 두 번째 호출: save_profile → 성공
        mock_api.side_effect = ["user@example.com", {"name": "user", "saved": True}]
        say = MagicMock()
        handle_profile(
            command="profile save", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert mock_api.call_count == 2
        assert "user" in say.call_args[1]["text"]
        assert "저장" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_profile_save_no_arg_email_not_found(self, mock_api):
        """profile save (인자 없음) + 이메일 없음 → 이름 입력 안내"""
        mock_api.return_value = None
        say = MagicMock()
        handle_profile(
            command="profile save", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "이메일" in say.call_args[1]["text"]
        assert "직접 지정" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._handle_profile_delete_ui")
    def test_profile_delete_no_arg_shows_ui(self, mock_delete_ui):
        """profile delete (인자 없음) → 삭제 버튼 UI 표시"""
        say = MagicMock()
        handle_profile(
            command="profile delete", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_delete_ui.assert_called_once_with(say, "ts1")

    def test_profile_change_no_arg(self):
        """profile change 인자 없으면 안내 메시지"""
        say = MagicMock()
        handle_profile(
            command="profile change", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "이름을 입력" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_soul_service_error_handled(self, mock_api):
        """SoulServiceError 발생 시 에러 메시지 표시"""
        from seosoyoung.slackbot.soulstream.service_client import SoulServiceError
        mock_api.side_effect = SoulServiceError("프로필을 찾을 수 없습니다: bad")
        say = MagicMock()
        handle_profile(
            command="profile delete bad", say=say, thread_ts="ts1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "❌" in say.call_args[1]["text"]
        assert "프로필을 찾을 수 없습니다" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
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


class TestSanitizeEmailToProfileName:
    def test_basic_email(self):
        """user@example.com → user"""
        assert _sanitize_email_to_profile_name("user@example.com") == "user"

    def test_no_at_sign(self):
        """@ 없는 경우 전체를 local로 사용"""
        assert _sanitize_email_to_profile_name("just_a_name") == "just_a_name"

    def test_dots_replaced(self):
        """점은 언더스코어로 대체"""
        result = _sanitize_email_to_profile_name("user.name@example.com")
        assert "." not in result
        assert "user" in result

    def test_digit_prefix_gets_p_prefix(self):
        """숫자로 시작하면 p_ 접두사"""
        result = _sanitize_email_to_profile_name("123user@example.com")
        assert result.startswith("p_")

    def test_max_length_64(self):
        """64자 초과 이름은 잘림"""
        long_local = "a" * 100
        result = _sanitize_email_to_profile_name(f"{long_local}@example.com")
        assert len(result) <= 64

    def test_empty_local_fallback(self):
        """빈 local 부분이면 fallback"""
        result = _sanitize_email_to_profile_name("@example.com")
        assert result == "profile"

    def test_special_chars_sanitized(self):
        """특수문자는 언더스코어로 대체"""
        result = _sanitize_email_to_profile_name("user+tag@example.com")
        assert "+" not in result


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


def _make_session(**overrides):
    """테스트용 Session mock 생성"""
    defaults = {
        "session_id": "claude-session-abc",
        "thread_ts": "1234567890.123456",
        "channel_id": "C08TEST",
        "username": "testuser",
        "user_id": "U123",
        "role": "admin",
        "message_count": 5,
        "created_at": "2026-03-06T10:00:00+00:00",
        "updated_at": "2026-03-06T10:05:00+00:00",
        "source_type": "thread",
    }
    defaults.update(overrides)
    session = MagicMock()
    for k, v in defaults.items():
        setattr(session, k, v)
    return session


class TestHandleSessionInfo:
    def _call(self, *, say=None, ts="ts1", thread_ts="thread1",
              session_manager=None, check_permission=None,
              get_agent_session_id=None, **kwargs):
        """핸들러 호출 헬퍼"""
        handle_session_info(
            say=say or MagicMock(),
            ts=ts,
            thread_ts=thread_ts,
            session_manager=session_manager or MagicMock(),
            client=MagicMock(),
            user_id="U1",
            check_permission=check_permission or MagicMock(return_value=True),
            get_agent_session_id=get_agent_session_id,
        )

    def test_permission_denied(self):
        """관리자 권한이 없으면 거부"""
        say = MagicMock()
        handle_session_info(
            say=say, ts="ts1", thread_ts=None,
            session_manager=MagicMock(),
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    def test_no_session_found(self):
        """세션이 없는 스레드에서 실행 시 안내 메시지"""
        say = MagicMock()
        sm = MagicMock()
        sm.get.return_value = None
        self._call(say=say, thread_ts="thread1", session_manager=sm)
        text = say.call_args[1]["text"]
        assert "세션이 없습니다" in text
        assert "thread1" in text

    def test_session_found_with_all_ids(self):
        """세션이 있고, agent_session_id도 있을 때 모든 ID를 표시"""
        say = MagicMock()
        session = _make_session()
        sm = MagicMock()
        sm.get.return_value = session
        get_agent = MagicMock(return_value="agent-session-xyz")

        self._call(
            say=say, thread_ts="1234567890.123456",
            session_manager=sm, get_agent_session_id=get_agent,
        )

        text = say.call_args[1]["text"]
        assert "claude-session-abc" in text
        assert "agent-session-xyz" in text
        assert "1234567890.123456" in text
        assert "C08TEST" in text
        assert "testuser" in text
        assert "admin" in text
        assert "실행 중" in text

    def test_session_found_no_agent_session(self):
        """세션은 있지만 agent_session_id가 없을 때 (대기 상태)"""
        say = MagicMock()
        session = _make_session(role="viewer", message_count=0, source_type="channel")
        sm = MagicMock()
        sm.get.return_value = session
        get_agent = MagicMock(return_value=None)

        self._call(
            say=say, thread_ts="1234567890.123456",
            session_manager=sm, get_agent_session_id=get_agent,
        )

        text = say.call_args[1]["text"]
        assert "실행 중 아님" in text
        assert "대기" in text

    def test_no_thread_ts_uses_ts(self):
        """thread_ts가 없으면 ts를 사용"""
        say = MagicMock()
        sm = MagicMock()
        sm.get.return_value = None
        self._call(say=say, ts="ts1", thread_ts=None, session_manager=sm)
        sm.get.assert_called_once_with("ts1")

    def test_no_get_agent_session_id(self):
        """get_agent_session_id가 전달되지 않아도 동작"""
        say = MagicMock()
        session = _make_session(session_id=None, username="", user_id="")
        sm = MagicMock()
        sm.get.return_value = session

        self._call(say=say, ts="ts1", thread_ts=None, session_manager=sm)

        text = say.call_args[1]["text"]
        assert "세션 정보" in text
        assert "실행 중 아님" in text

    def test_error_handling(self):
        """session_manager.get()이 예외를 던져도 에러 메시지를 반환"""
        say = MagicMock()
        sm = MagicMock()
        sm.get.side_effect = RuntimeError("disk error")

        self._call(say=say, thread_ts="thread1", session_manager=sm)

        text = say.call_args[1]["text"]
        assert "오류가 발생했습니다" in text

    def test_dispatched_via_try_handle_command(self):
        """try_handle_command에서 session-info가 정상 디스패치되는지 확인"""
        say = MagicMock()
        sm = MagicMock()
        sm.get.return_value = None
        deps = _make_deps(session_manager=sm)

        result = try_handle_command(
            "session-info", "", "C1", "ts1", "thread1",
            "U1", say, MagicMock(), deps,
        )

        assert result is True
        assert say.called


class TestHandleSetToken:
    def test_permission_denied(self):
        """관리자 권한 없으면 거부"""
        say = MagicMock()
        handle_set_token(
            command="set-token sk-ant-oat01-xxx", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    def test_no_token_argument(self):
        """토큰 인자 없으면 안내 메시지"""
        say = MagicMock()
        handle_set_token(
            command="set-token", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "토큰을 입력해주세요" in say.call_args[1]["text"]

    def test_invalid_token_format(self):
        """유효하지 않은 토큰 형식 거부"""
        say = MagicMock()
        handle_set_token(
            command="set-token bad-token", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "유효하지 않은 토큰 형식" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_set_token_success(self, mock_api):
        """토큰 설정 성공"""
        mock_api.return_value = {"success": True, "message": "토큰이 설정되었습니다."}
        say = MagicMock()
        handle_set_token(
            command="set-token sk-ant-oat01-xxx", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_api.assert_called_once()
        assert "토큰이 설정되었습니다" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_set_token_api_failure(self, mock_api):
        """토큰 설정 API 실패"""
        mock_api.return_value = {"success": False, "error": "토큰 검증 실패"}
        say = MagicMock()
        handle_set_token(
            command="set-token sk-ant-oat01-xxx", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "토큰 설정 실패" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_set_token_connection_error(self, mock_api):
        """soulstream 연결 실패"""
        mock_api.side_effect = ConnectionError("connection refused")
        say = MagicMock()
        handle_set_token(
            command="set-token sk-ant-oat01-xxx", say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "soulstream 연결 실패" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_set_token_with_thread_ts(self, mock_api):
        """thread_ts가 있으면 해당 스레드에 응답"""
        mock_api.return_value = {"success": True}
        say = MagicMock()
        handle_set_token(
            command="set-token sk-ant-oat01-xxx", say=say, ts="ts1", thread_ts="thread1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert say.call_args[1]["thread_ts"] == "thread1"


class TestHandleClearToken:
    def test_permission_denied(self):
        """관리자 권한 없으면 거부"""
        say = MagicMock()
        handle_clear_token(
            say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_clear_token_success(self, mock_api):
        """토큰 삭제 성공"""
        mock_api.return_value = {"success": True, "message": "토큰이 삭제되었습니다."}
        say = MagicMock()
        handle_clear_token(
            say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        mock_api.assert_called_once()
        assert "토큰이 삭제되었습니다" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_clear_token_connection_error(self, mock_api):
        """soulstream 연결 실패"""
        mock_api.side_effect = ConnectionError("connection refused")
        say = MagicMock()
        handle_clear_token(
            say=say, ts="ts1", thread_ts=None,
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert "soulstream 연결 실패" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.commands._run_soul_api")
    def test_clear_token_with_thread_ts(self, mock_api):
        """thread_ts가 있으면 해당 스레드에 응답"""
        mock_api.return_value = {"success": True, "message": "삭제됨"}
        say = MagicMock()
        handle_clear_token(
            say=say, ts="ts1", thread_ts="thread1",
            client=MagicMock(), user_id="U1",
            check_permission=MagicMock(return_value=True),
        )
        assert say.call_args[1]["thread_ts"] == "thread1"


class TestHandleCleanup:
    def test_permission_denied(self):
        say = MagicMock()
        handle_cleanup(
            command="cleanup", say=say, ts="ts1", client=MagicMock(),
            user_id="U1", session_manager=MagicMock(),
            check_permission=MagicMock(return_value=False),
        )
        assert "관리자 권한" in say.call_args[1]["text"]
