"""handlers/auth.py 단위 테스트

setup-token, clear-token 핸들러와 check_auth_session 함수를 테스트합니다.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from seosoyoung.slackbot.handlers.auth import (
    handle_setup_token,
    handle_clear_token,
    check_auth_session,
    get_active_auth_sessions,
    clear_auth_sessions,
    _active_auth_sessions,
)


@pytest.fixture(autouse=True)
def clear_sessions():
    """각 테스트 후 인증 세션 초기화"""
    yield
    clear_auth_sessions()


class TestHandleSetupToken:
    """setup-token 명령어 핸들러 테스트"""

    def test_requires_permission(self):
        """권한이 없으면 거부"""
        say = MagicMock()
        client = MagicMock()
        check_permission = MagicMock(return_value=False)

        handle_setup_token(
            say=say,
            ts="1234",
            thread_ts=None,
            channel="C123",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        assert "관리자 권한" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_success_creates_auth_session(self, mock_api):
        """성공 시 인증 세션 생성"""
        mock_api.return_value = {
            "session_id": "auth-session-123",
            "auth_url": "https://claude.ai/oauth/authorize?xyz",
        }
        say = MagicMock(return_value={"ts": "thread-ts-456"})
        client = MagicMock()
        check_permission = MagicMock(return_value=True)

        handle_setup_token(
            say=say,
            ts="1234",
            thread_ts=None,
            channel="C123",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        text = say.call_args[1]["text"]
        assert "🔐" in text
        assert "https://claude.ai/oauth/authorize?xyz" in text
        assert "5분" in text

        # 인증 세션이 등록되었는지 확인
        sessions = get_active_auth_sessions()
        assert "thread-ts-456" in sessions
        assert sessions["thread-ts-456"] == "auth-session-123"

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_api_error(self, mock_api):
        """API 오류 시 에러 메시지"""
        from seosoyoung.slackbot.soulstream.service_client import SoulServiceError
        mock_api.side_effect = SoulServiceError("서버 오류")

        say = MagicMock()
        client = MagicMock()
        check_permission = MagicMock(return_value=True)

        handle_setup_token(
            say=say,
            ts="1234",
            thread_ts=None,
            channel="C123",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        assert "❌" in say.call_args[1]["text"]
        assert "서버 오류" in say.call_args[1]["text"]


class TestHandleClearToken:
    """clear-token 명령어 핸들러 테스트"""

    def test_requires_permission(self):
        """권한이 없으면 거부"""
        say = MagicMock()
        client = MagicMock()
        check_permission = MagicMock(return_value=False)

        handle_clear_token(
            say=say,
            ts="1234",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        assert "관리자 권한" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_success(self, mock_api):
        """성공 시 완료 메시지"""
        mock_api.return_value = {"deleted": True}
        say = MagicMock()
        client = MagicMock()
        check_permission = MagicMock(return_value=True)

        handle_clear_token(
            say=say,
            ts="1234",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        assert "✅" in say.call_args[1]["text"]
        assert "삭제" in say.call_args[1]["text"]

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_api_error(self, mock_api):
        """API 오류 시 에러 메시지"""
        from seosoyoung.slackbot.soulstream.service_client import SoulServiceError
        mock_api.side_effect = SoulServiceError("토큰 없음")

        say = MagicMock()
        client = MagicMock()
        check_permission = MagicMock(return_value=True)

        handle_clear_token(
            say=say,
            ts="1234",
            client=client,
            user_id="U123",
            check_permission=check_permission,
        )

        say.assert_called_once()
        assert "❌" in say.call_args[1]["text"]
        assert "토큰 없음" in say.call_args[1]["text"]


class TestCheckAuthSession:
    """check_auth_session 함수 테스트"""

    def test_no_active_session(self):
        """활성 인증 세션이 없으면 False 반환"""
        result = check_auth_session(
            thread_ts="thread-123",
            text="some-code",
            say=MagicMock(),
            client=MagicMock(),
            dependencies={},
        )
        assert result is False

    def test_empty_code_ignored(self):
        """빈 코드는 무시"""
        _active_auth_sessions["thread-123"] = "session-123"

        result = check_auth_session(
            thread_ts="thread-123",
            text="   ",
            say=MagicMock(),
            client=MagicMock(),
            dependencies={},
        )
        assert result is False
        # 세션이 유지되어야 함
        assert "thread-123" in _active_auth_sessions

    def test_long_code_ignored(self):
        """200자 초과 코드는 무시"""
        _active_auth_sessions["thread-123"] = "session-123"

        result = check_auth_session(
            thread_ts="thread-123",
            text="x" * 250,
            say=MagicMock(),
            client=MagicMock(),
            dependencies={},
        )
        assert result is False
        assert "thread-123" in _active_auth_sessions

    def test_code_with_spaces_ignored(self):
        """공백이 포함된 코드는 무시"""
        _active_auth_sessions["thread-123"] = "session-123"

        result = check_auth_session(
            thread_ts="thread-123",
            text="hello world",
            say=MagicMock(),
            client=MagicMock(),
            dependencies={},
        )
        assert result is False
        assert "thread-123" in _active_auth_sessions

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_success(self, mock_api):
        """인증 성공 시 세션 정리"""
        mock_api.return_value = {"success": True, "expires_at": "1년"}
        _active_auth_sessions["thread-123"] = "session-123"

        say = MagicMock()
        result = check_auth_session(
            thread_ts="thread-123",
            text="valid-auth-code",
            say=say,
            client=MagicMock(),
            dependencies={},
        )

        assert result is True
        say.assert_called_once()
        assert "✅" in say.call_args[1]["text"]
        assert "완료" in say.call_args[1]["text"]
        # 세션이 정리되어야 함
        assert "thread-123" not in _active_auth_sessions

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_failure(self, mock_api):
        """인증 실패 시 에러 메시지"""
        mock_api.return_value = {"success": False, "error": "잘못된 코드"}
        _active_auth_sessions["thread-123"] = "session-123"

        say = MagicMock()
        result = check_auth_session(
            thread_ts="thread-123",
            text="invalid-code",
            say=say,
            client=MagicMock(),
            dependencies={},
        )

        assert result is True
        say.assert_called_once()
        assert "❌" in say.call_args[1]["text"]
        # 실패해도 세션은 정리됨
        assert "thread-123" not in _active_auth_sessions

    @patch("seosoyoung.slackbot.handlers.auth._run_soul_api")
    def test_api_error_cleans_session(self, mock_api):
        """API 오류 시에도 세션 정리"""
        from seosoyoung.slackbot.soulstream.service_client import SoulServiceError
        mock_api.side_effect = SoulServiceError("네트워크 오류")
        _active_auth_sessions["thread-123"] = "session-123"

        say = MagicMock()
        result = check_auth_session(
            thread_ts="thread-123",
            text="some-code",
            say=say,
            client=MagicMock(),
            dependencies={},
        )

        assert result is True
        say.assert_called_once()
        assert "❌" in say.call_args[1]["text"]
        # 오류 시에도 세션은 정리됨
        assert "thread-123" not in _active_auth_sessions


class TestMentionRouting:
    """멘션 핸들러 라우팅 테스트"""

    def test_setup_token_in_admin_commands(self):
        """setup-token이 관리자 명령어로 등록됨"""
        from seosoyoung.slackbot.handlers.mention import _is_admin_command
        assert _is_admin_command("setup-token")

    def test_clear_token_in_admin_commands(self):
        """clear-token이 관리자 명령어로 등록됨"""
        from seosoyoung.slackbot.handlers.mention import _is_admin_command
        assert _is_admin_command("clear-token")

    def test_setup_token_in_dispatch(self):
        """setup-token이 디스패치 테이블에 등록됨"""
        from seosoyoung.slackbot.handlers.mention import _COMMAND_DISPATCH
        assert "setup-token" in _COMMAND_DISPATCH

    def test_clear_token_in_dispatch(self):
        """clear-token이 디스패치 테이블에 등록됨"""
        from seosoyoung.slackbot.handlers.mention import _COMMAND_DISPATCH
        assert "clear-token" in _COMMAND_DISPATCH
