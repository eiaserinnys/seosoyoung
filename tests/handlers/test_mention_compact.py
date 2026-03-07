"""compact 커맨드 테스트"""

import pytest
from unittest.mock import MagicMock

from seosoyoung.slackbot.handlers.mention import register_mention_handlers


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

    def test_compact_without_thread_shows_guide(self):
        """스레드 밖에서 compact 호출 시 안내 메시지"""
        deps = _make_dependencies()
        handler = _register_and_get_handler(deps)

        event = {
            "user": "U123",
            "text": "<@BOT> compact",
            "channel": "C123",
            "ts": "1234567890.000000",
        }
        say = MagicMock()
        client = MagicMock()

        handler(event, say, client)

        say.assert_called_once()
        call_kwargs = say.call_args[1]
        assert "스레드에서 사용" in call_kwargs["text"]

    def test_compact_in_thread_without_session(self):
        """스레드에서 compact 호출했지만 세션이 없을 때"""
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

        say.assert_called_once()
        call_kwargs = say.call_args[1]
        assert "활성 세션" in call_kwargs["text"]

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
