"""세션 관리 테스트"""

import json
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.claude.session import Session, SessionManager


class TestSession:
    """Session 데이터클래스 테스트"""

    def test_session_creation(self):
        """세션 생성 테스트"""
        session = Session(thread_ts="1234567890.123456", channel_id="C12345")

        assert session.thread_ts == "1234567890.123456"
        assert session.channel_id == "C12345"
        assert session.session_id is None
        assert session.message_count == 0
        assert session.created_at != ""
        assert session.updated_at != ""

    def test_session_with_session_id(self):
        """세션 ID가 있는 경우"""
        session = Session(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            session_id="abc-123"
        )

        assert session.session_id == "abc-123"


class TestSessionManager:
    """SessionManager 테스트"""

    @pytest.fixture
    def temp_dir(self):
        """임시 디렉토리 생성"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_dir):
        """테스트용 세션 매니저"""
        return SessionManager(session_dir=temp_dir)

    def test_create_session(self, manager):
        """세션 생성 테스트"""
        session = manager.create(
            thread_ts="1234567890.123456",
            channel_id="C12345"
        )

        assert session.thread_ts == "1234567890.123456"
        assert session.channel_id == "C12345"
        assert manager.exists("1234567890.123456")

    def test_get_session(self, manager):
        """세션 조회 테스트"""
        manager.create(thread_ts="1234567890.123456", channel_id="C12345")

        session = manager.get("1234567890.123456")

        assert session is not None
        assert session.thread_ts == "1234567890.123456"

    def test_get_nonexistent_session(self, manager):
        """존재하지 않는 세션 조회"""
        session = manager.get("nonexistent")

        assert session is None

    def test_update_session_id(self, manager):
        """세션 ID 업데이트 테스트"""
        manager.create(thread_ts="1234567890.123456", channel_id="C12345")

        session = manager.update_session_id("1234567890.123456", "new-session-id")

        assert session.session_id == "new-session-id"

        # 파일에도 저장되었는지 확인
        manager._cache.clear()
        reloaded = manager.get("1234567890.123456")
        assert reloaded.session_id == "new-session-id"

    def test_increment_message_count(self, manager):
        """메시지 카운트 증가 테스트"""
        manager.create(thread_ts="1234567890.123456", channel_id="C12345")

        manager.increment_message_count("1234567890.123456")
        manager.increment_message_count("1234567890.123456")

        session = manager.get("1234567890.123456")
        assert session.message_count == 2

    def test_count(self, manager):
        """세션 수 카운트 테스트"""
        assert manager.count() == 0

        manager.create(thread_ts="1111111111.111111", channel_id="C1")
        manager.create(thread_ts="2222222222.222222", channel_id="C2")

        assert manager.count() == 2

    def test_list_active(self, manager):
        """활성 세션 목록 테스트"""
        manager.create(thread_ts="1111111111.111111", channel_id="C1")
        manager.create(thread_ts="2222222222.222222", channel_id="C2")

        sessions = manager.list_active()

        assert len(sessions) == 2
        thread_ts_list = [s.thread_ts for s in sessions]
        assert "1111111111.111111" in thread_ts_list
        assert "2222222222.222222" in thread_ts_list

    def test_session_persistence(self, temp_dir):
        """세션 파일 저장/로드 테스트"""
        # 첫 번째 매니저로 세션 생성
        manager1 = SessionManager(session_dir=temp_dir)
        manager1.create(thread_ts="1234567890.123456", channel_id="C12345")
        manager1.update_session_id("1234567890.123456", "persistent-id")

        # 새 매니저로 로드
        manager2 = SessionManager(session_dir=temp_dir)
        session = manager2.get("1234567890.123456")

        assert session is not None
        assert session.session_id == "persistent-id"

    def test_session_file_format(self, manager, temp_dir):
        """세션 파일 포맷 확인"""
        manager.create(thread_ts="1234567890.123456", channel_id="C12345")

        # 파일이 생성되었는지 확인
        files = list(temp_dir.glob("session_*.json"))
        assert len(files) == 1

        # JSON 형식 확인
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["thread_ts"] == "1234567890.123456"
        assert data["channel_id"] == "C12345"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
