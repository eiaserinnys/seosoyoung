"""Phase 4 테스트: 세션 관리"""

import pytest

from seosoyoung.rescue.session import Session, SessionManager


class TestSessionManager:
    """세션 매니저 테스트"""

    def test_session_create_and_retrieve(self):
        """세션 생성 및 조회"""
        manager = SessionManager()

        session = manager.create("ts_001", "C_CH1")

        assert session.thread_ts == "ts_001"
        assert session.channel_id == "C_CH1"
        assert session.session_id is None
        assert session.message_count == 0
        assert session.created_at != ""

        # 조회
        retrieved = manager.get("ts_001")
        assert retrieved is not None
        assert retrieved.thread_ts == "ts_001"

        # 존재하지 않는 세션
        assert manager.get("nonexistent") is None

    def test_session_id_update(self):
        """세션 ID 업데이트"""
        manager = SessionManager()
        manager.create("ts_002", "C_CH2")

        # 초기 세션 ID는 None
        session = manager.get("ts_002")
        assert session.session_id is None

        # 업데이트
        result = manager.update_session_id("ts_002", "claude_session_abc")
        assert result is not None
        assert result.session_id == "claude_session_abc"

        # 다시 조회해도 반영됨
        session2 = manager.get("ts_002")
        assert session2.session_id == "claude_session_abc"

        # 없는 세션에 업데이트 시도
        assert manager.update_session_id("nonexistent", "xyz") is None

    def test_session_count(self):
        """세션 수 카운트"""
        manager = SessionManager()

        assert manager.count() == 0

        manager.create("ts_a", "C_1")
        assert manager.count() == 1

        manager.create("ts_b", "C_2")
        assert manager.count() == 2

        # 같은 키로 생성하면 덮어쓰기
        manager.create("ts_a", "C_3")
        assert manager.count() == 2

    def test_message_count_increment(self):
        """메시지 카운트 증가"""
        manager = SessionManager()
        manager.create("ts_inc", "C_INC")

        session = manager.get("ts_inc")
        assert session.message_count == 0

        manager.increment_message_count("ts_inc")
        assert session.message_count == 1

        manager.increment_message_count("ts_inc")
        manager.increment_message_count("ts_inc")
        assert session.message_count == 3

        # 없는 세션에 증가 시도
        assert manager.increment_message_count("nonexistent") is None
