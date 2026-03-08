"""Phase 3 테스트: 응답 처리"""

import threading
from unittest.mock import MagicMock

import pytest


class TestLongMessageSplit:
    """긴 메시지 분할 테스트"""

    def test_long_message_split(self):
        """3900자 초과 메시지 분할 전송"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        say = MagicMock()
        long_text = "A" * 8000

        app._send_long_message(say, long_text, "thread_123")

        # 최소 2번 이상 호출
        assert say.call_count >= 2
        # 첫 번째 chunk는 3900자 이하
        first_call_text = say.call_args_list[0].kwargs.get("text", say.call_args_list[0][1].get("text", ""))
        assert len(first_call_text) <= 3900

    def test_short_message_single_call(self):
        """3900자 이하는 한 번에 전송"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        say = MagicMock()
        short_text = "짧은 메시지"

        app._send_long_message(say, short_text, "thread_123")

        assert say.call_count == 1


class TestCompactCallback:
    """on_compact 콜백 테스트"""

    def test_compact_callback_in_signature(self):
        """on_compact는 ClaudeRunner.run()에 전달 가능"""
        from seosoyoung.rescue.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner()

        # on_compact 콜백을 run()에 전달할 수 있는지 확인
        # (실제 SDK 호출 없이 시그니처 확인)
        import inspect
        sig = inspect.signature(runner.run)
        param_names = list(sig.parameters.keys())
        assert "on_compact" in param_names
        # on_progress는 Phase 4에서 제거됨
        assert "on_progress" not in param_names


class TestErrorResultDisplay:
    """에러 결과 표시 테스트"""

    def test_error_result_display(self):
        """에러 메시지가 적절히 포맷팅"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        say = MagicMock()
        client = MagicMock()

        app._handle_error(
            "테스트 에러", "C123", "thread_123", "msg_ts_123", say, client,
            is_thread_reply=False,
        )

        # chat_update가 호출됨
        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args.kwargs
        assert "❌" in call_kwargs["text"]
        assert "테스트 에러" in call_kwargs["text"]
        # 채널 최초 응답이므로 continuation hint 포함
        assert "이어가려면" in call_kwargs["text"]

    def test_error_in_thread_no_hint(self):
        """스레드 내 에러에는 continuation hint 없음"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        say = MagicMock()
        client = MagicMock()

        app._handle_error(
            "스레드 에러", "C123", "thread_123", "msg_ts_123", say, client,
            is_thread_reply=True,
        )

        call_kwargs = client.chat_update.call_args.kwargs
        assert "❌" in call_kwargs["text"]
        assert "이어가려면" not in call_kwargs["text"]


class TestEmptyResponseHandling:
    """빈 응답 처리 테스트"""

    def test_empty_response_handling(self):
        """빈 응답은 (중단됨) 메시지로 처리"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.claude.engine_types import EngineResult
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        say = MagicMock()
        client = MagicMock()

        # 빈 output의 성공 결과
        result = EngineResult(success=True, output="", session_id="sess_1")

        app._handle_success(
            result, "C123", "thread_123", "msg_ts_123", say, client,
        )

        # (중단됨) 메시지로 처리됨
        client.chat_update.assert_called_once()
        call_kwargs = client.chat_update.call_args.kwargs
        assert "중단됨" in call_kwargs["text"]


class TestSlackContextBlock:
    """슬랙 컨텍스트 블록 테스트"""

    def test_slack_context_block(self):
        """슬랙 컨텍스트 블록에 채널/유저/스레드 정보 포함"""
        from seosoyoung.rescue.main import RescueBotApp
        from seosoyoung.rescue.session import SessionManager

        app = RescueBotApp.__new__(RescueBotApp)
        app.sessions = SessionManager()
        app._thread_locks = {}
        app._locks_lock = threading.Lock()
        app._pending_prompts = {}
        app._pending_lock = threading.Lock()
        app._active_runners = {}
        app._runners_lock = threading.Lock()
        app.bot_user_id = "U_BOT"

        ctx = app._build_slack_context("C_CHANNEL", "U_USER", "1234567890.000001")

        assert "<slack-context>" in ctx
        assert "C_CHANNEL" in ctx
        assert "U_USER" in ctx
        assert "1234567890.000001" in ctx
        assert "</slack-context>" in ctx
