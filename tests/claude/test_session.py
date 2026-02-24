"""세션 관리 테스트"""

import json
import tempfile
from pathlib import Path
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

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

    def test_session_with_role(self):
        """역할 정보 포함 세션 생성"""
        session = Session(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            user_id="U12345",
            username="testuser",
            role="admin"
        )

        assert session.user_id == "U12345"
        assert session.username == "testuser"
        assert session.role == "admin"

    def test_session_default_role(self):
        """기본 역할은 viewer"""
        session = Session(thread_ts="1234567890.123456", channel_id="C12345")

        assert session.role == "viewer"
        assert session.user_id == ""
        assert session.username == ""

    def test_session_source_type_default(self):
        """source_type 기본값은 thread"""
        session = Session(thread_ts="1234567890.123456", channel_id="C12345")
        assert session.source_type == "thread"

    def test_session_source_type_channel(self):
        """source_type을 channel로 설정"""
        session = Session(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            source_type="channel",
        )
        assert session.source_type == "channel"

    def test_session_source_type_hybrid(self):
        """source_type을 hybrid로 설정"""
        session = Session(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            source_type="hybrid",
        )
        assert session.source_type == "hybrid"

    def test_session_last_seen_ts_default(self):
        """last_seen_ts 기본값은 빈 문자열"""
        session = Session(thread_ts="1234567890.123456", channel_id="C12345")
        assert session.last_seen_ts == ""

    def test_session_last_seen_ts(self):
        """last_seen_ts 설정"""
        session = Session(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            last_seen_ts="1234567890.999999",
        )
        assert session.last_seen_ts == "1234567890.999999"


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

    def test_create_session_with_role(self, manager):
        """역할 정보 포함 세션 생성 테스트"""
        session = manager.create(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            user_id="U12345",
            username="testuser",
            role="admin"
        )

        assert session.user_id == "U12345"
        assert session.username == "testuser"
        assert session.role == "admin"

        # 파일에서 다시 로드해도 역할 정보 유지
        manager._cache.clear()
        reloaded = manager.get("1234567890.123456")
        assert reloaded.role == "admin"
        assert reloaded.username == "testuser"

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

    def test_create_session_with_source_type(self, manager):
        """source_type 포함 세션 생성 및 영속성 테스트"""
        session = manager.create(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            source_type="channel",
            last_seen_ts="1234567890.000001",
        )

        assert session.source_type == "channel"
        assert session.last_seen_ts == "1234567890.000001"

        # 파일에서 다시 로드해도 유지
        manager._cache.clear()
        reloaded = manager.get("1234567890.123456")
        assert reloaded.source_type == "channel"
        assert reloaded.last_seen_ts == "1234567890.000001"

    def test_update_last_seen_ts(self, manager):
        """last_seen_ts 업데이트"""
        manager.create(
            thread_ts="1234567890.123456",
            channel_id="C12345",
        )

        session = manager.update_last_seen_ts("1234567890.123456", "1234567890.999999")
        assert session.last_seen_ts == "1234567890.999999"

        # 파일에서 다시 로드해도 유지
        manager._cache.clear()
        reloaded = manager.get("1234567890.123456")
        assert reloaded.last_seen_ts == "1234567890.999999"

    def test_update_user(self, manager):
        """user_id/username/role 업데이트"""
        manager.create(
            thread_ts="1234567890.123456",
            channel_id="C12345",
        )
        assert manager.get("1234567890.123456").user_id == ""

        session = manager.update_user(
            "1234567890.123456",
            user_id="U999",
            username="newuser",
            role="admin",
        )
        assert session.user_id == "U999"
        assert session.username == "newuser"
        assert session.role == "admin"

        # 파일에서 다시 로드해도 유지
        manager._cache.clear()
        reloaded = manager.get("1234567890.123456")
        assert reloaded.user_id == "U999"
        assert reloaded.username == "newuser"
        assert reloaded.role == "admin"

    def test_update_user_nonexistent(self, manager):
        """존재하지 않는 세션의 사용자 업데이트는 None 반환"""
        result = manager.update_user("nonexistent.123", user_id="U1")
        assert result is None

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

    def test_get_corrupted_session_file(self, manager, temp_dir):
        """손상된 세션 파일 로드 시 None 반환"""
        # 손상된 JSON 파일 생성
        corrupted_file = temp_dir / "session_corrupted_123.json"
        corrupted_file.write_text("{ invalid json }", encoding="utf-8")

        # 로드 시 None 반환 (에러 로그만 남김)
        session = manager.get("corrupted.123")
        assert session is None

    def test_list_active_with_corrupted_file(self, manager, temp_dir):
        """손상된 파일이 있어도 정상 파일 목록 반환"""
        # 정상 세션 생성
        manager.create(thread_ts="1111111111.111111", channel_id="C1")

        # 손상된 파일 생성
        corrupted_file = temp_dir / "session_corrupted_2.json"
        corrupted_file.write_text("{ invalid }", encoding="utf-8")

        # 정상 세션만 반환
        sessions = manager.list_active()
        assert len(sessions) == 1
        assert sessions[0].thread_ts == "1111111111.111111"

    def test_save_to_readonly_directory(self, temp_dir):
        """읽기 전용 디렉토리에 저장 시 에러 처리"""
        import os
        import stat

        # 테스트용 읽기 전용 디렉토리 생성
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()

        manager = SessionManager(session_dir=readonly_dir)

        # 디렉토리를 읽기 전용으로 변경
        os.chmod(readonly_dir, stat.S_IRUSR | stat.S_IXUSR)

        try:
            # 저장 시도 - 실패해도 예외 발생 안 함
            session = Session(thread_ts="test.123", channel_id="C1")
            manager._save(session)  # 에러 로그만 남김
        finally:
            # 권한 복원
            os.chmod(readonly_dir, stat.S_IRWXU)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
