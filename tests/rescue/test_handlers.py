"""Phase 2 테스트: main.py 핸들러"""

import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestHandleMention:
    """멘션 핸들러 테스트"""

    def _make_app(self):
        """테스트용 RescueBotApp (SessionManager 사용)"""
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
        app.bot_user_id = "U_RESCUE_BOT"
        return app

    def test_handle_mention_creates_session(self):
        """멘션 시 세션 생성"""
        app = self._make_app()

        event = {
            "user": "U123",
            "text": "<@U_RESCUE_BOT> hello",
            "channel": "C123",
            "ts": "1234567890.000001",
        }

        # 세션이 없는 상태에서 멘션 → 세션 생성
        thread_ts = event["ts"]
        session = app._get_or_create_session(thread_ts, event["channel"])

        assert session is not None
        assert session.thread_ts == thread_ts
        assert session.channel_id == event["channel"]

    def test_handle_mention_with_existing_session(self):
        """기존 세션 스레드에서 멘션"""
        app = self._make_app()

        thread_ts = "1234567890.000001"
        session = app._get_or_create_session(thread_ts, "C123")

        # 동일 스레드에서 다시 조회
        existing = app._get_session(thread_ts)
        assert existing is not None
        assert existing.thread_ts == session.thread_ts

    def test_handle_mention_bot_message_ignored(self):
        """봇 메시지는 무시해야 함"""
        app = self._make_app()

        # bot_id가 있는 이벤트
        event = {
            "user": "U123",
            "text": "<@U_RESCUE_BOT> hello",
            "channel": "C123",
            "ts": "1234567890.000001",
            "bot_id": "B_SOME_BOT",
        }
        assert app._should_ignore_event(event) is True

        # subtype가 bot_message인 이벤트
        event2 = {
            "user": "U123",
            "text": "<@U_RESCUE_BOT> hello",
            "channel": "C123",
            "ts": "1234567890.000002",
            "subtype": "bot_message",
        }
        assert app._should_ignore_event(event2) is True

    def test_handle_message_with_session(self):
        """세션 있는 스레드 메시지 처리"""
        app = self._make_app()

        thread_ts = "1234567890.000001"
        app._get_or_create_session(thread_ts, "C123")

        # 세션이 있는 스레드의 일반 메시지
        session = app._get_session(thread_ts)
        assert session is not None

    def test_handle_message_no_session_ignored(self):
        """세션 없는 스레드 메시지 무시"""
        app = self._make_app()

        # 세션이 없는 스레드
        session = app._get_session("nonexistent_thread")
        assert session is None

    def test_process_message_lock_busy(self):
        """락 획득 실패 시 안내 메시지"""
        app = self._make_app()

        thread_ts = "1234567890.000001"
        lock = app._get_thread_lock(thread_ts)

        # 락을 미리 획득
        lock.acquire()

        # 두 번째 acquire 시도는 실패해야 함
        assert lock.acquire(blocking=False) is False

        lock.release()

    def test_help_command(self):
        """help 명령어 인식"""
        app = self._make_app()
        text = "<@U_RESCUE_BOT> help"
        command = app._extract_command(text)
        assert command == "help"
