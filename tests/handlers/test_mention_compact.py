"""compact 커맨드 테스트"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from seosoyoung.handlers.mention import register_mention_handlers


def _make_dependencies():
    """테스트용 dependencies 생성"""
    session_manager = MagicMock()
    restart_manager = MagicMock()
    restart_manager.is_pending = False

    return {
        "session_manager": session_manager,
        "restart_manager": restart_manager,
        "get_running_session_count": MagicMock(return_value=0),
        "run_claude_in_session": MagicMock(),
        "check_permission": MagicMock(return_value=True),
        "get_user_role": MagicMock(return_value={"username": "tester", "role": "admin"}),
        "send_restart_confirmation": MagicMock(),
        "list_runner_ref": MagicMock(return_value=None),
    }


def _register_and_get_handler(dependencies):
    """핸들러 등록 후 handle_mention 함수 반환"""
    app = MagicMock()
    registered_handlers = {}

    def capture_handler(event_type):
        def decorator(func):
            registered_handlers[event_type] = func
            return func
        return decorator

    app.event = capture_handler
    register_mention_handlers(app, dependencies)
    return registered_handlers["app_mention"]


class TestCompactCommand:
    """compact 커맨드 테스트"""

    def test_compact_in_channel_shows_thread_message(self):
        """채널에서 compact 호출 시 '스레드에서 사용해주세요' 안내"""
        deps = _make_dependencies()
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000000",
            # thread_ts 없음 → 채널에서 호출
        }
        say = MagicMock()
        client = MagicMock()

        handler(event, say, client)

        say.assert_called_once()
        call_kwargs = say.call_args[1]
        assert "스레드에서 사용해주세요" in call_kwargs["text"]

    def test_compact_in_thread_no_session(self):
        """세션 없는 스레드에서 compact 호출 시 안내 메시지"""
        deps = _make_dependencies()
        deps["session_manager"].get.return_value = None
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        handler(event, say, client)

        # "활성 세션이 없습니다" 메시지 확인
        calls = say.call_args_list
        assert any("활성 세션이 없습니다" in str(c) for c in calls)

    def test_compact_in_thread_no_session_id(self):
        """세션은 있지만 session_id가 없는 경우"""
        deps = _make_dependencies()
        session = MagicMock()
        session.session_id = ""
        deps["session_manager"].get.return_value = session
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        handler(event, say, client)

        calls = say.call_args_list
        assert any("활성 세션이 없습니다" in str(c) for c in calls)

    def test_compact_success(self):
        """compact 성공 테스트"""
        deps = _make_dependencies()
        session = MagicMock()
        session.session_id = "test-session-id"
        deps["session_manager"].get.return_value = session
        deps["session_manager"].exists.return_value = True
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "new-session-id"

        mock_runner = MagicMock()
        mock_runner.compact_session = AsyncMock(return_value=mock_result)

        with patch("seosoyoung.claude.get_claude_runner", return_value=mock_runner):
            with patch("seosoyoung.handlers.mention.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = mock_result
                handler(event, say, client)

        calls = say.call_args_list
        # "컴팩트 중입니다..." 와 "컴팩트가 완료됐습니다." 두 번 호출
        assert len(calls) == 2
        assert "컴팩트 중입니다" in str(calls[0])
        assert "컴팩트가 완료됐습니다" in str(calls[1])

    def test_compact_updates_session_id(self):
        """compact 성공 시 session_id 업데이트"""
        deps = _make_dependencies()
        session = MagicMock()
        session.session_id = "old-session-id"
        deps["session_manager"].get.return_value = session
        deps["session_manager"].exists.return_value = True
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "new-session-id"

        with patch("seosoyoung.claude.get_claude_runner") as mock_get_runner:
            with patch("seosoyoung.handlers.mention.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = mock_result
                handler(event, say, client)

        deps["session_manager"].update_session_id.assert_called_once_with(
            "1234567890.000000", "new-session-id"
        )

    def test_compact_failure(self):
        """compact 실패 테스트"""
        deps = _make_dependencies()
        session = MagicMock()
        session.session_id = "test-session-id"
        deps["session_manager"].get.return_value = session
        deps["session_manager"].exists.return_value = True
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "세션을 찾을 수 없습니다"

        with patch("seosoyoung.claude.get_claude_runner") as mock_get_runner:
            with patch("seosoyoung.handlers.mention.asyncio") as mock_asyncio:
                mock_asyncio.run.return_value = mock_result
                handler(event, say, client)

        calls = say.call_args_list
        assert any("실패" in str(c) for c in calls)

    def test_compact_exception(self):
        """compact 실행 중 예외 테스트"""
        deps = _make_dependencies()
        session = MagicMock()
        session.session_id = "test-session-id"
        deps["session_manager"].get.return_value = session
        deps["session_manager"].exists.return_value = True
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        with patch("seosoyoung.claude.get_claude_runner", side_effect=RuntimeError("connection failed")):
            handler(event, say, client)

        calls = say.call_args_list
        assert any("오류" in str(c) for c in calls)

    def test_compact_in_help_text(self):
        """help 메시지에 compact 포함 확인"""
        deps = _make_dependencies()
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> help",
            "channel": "C123",
            "ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        handler(event, say, client)

        call_kwargs = say.call_args[1]
        assert "compact" in call_kwargs["text"]
