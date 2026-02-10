"""관찰 로그 저장소 단위 테스트"""

import json
from datetime import datetime, timezone

import pytest

from seosoyoung.memory.store import MemoryRecord, MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(base_dir=tmp_path)


@pytest.fixture
def sample_record():
    return MemoryRecord(
        user_id="U08HWT0C6K1",
        username="eias",
        observations="## [2026-02-10] Session Observations\n\n🔴 사용자는 커밋 메시지를 한글로 작성",
        observation_tokens=50,
        last_observed_at=datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc),
        total_sessions_observed=3,
        reflection_count=0,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )


class TestMemoryRecord:
    def test_to_meta_dict(self, sample_record):
        meta = sample_record.to_meta_dict()
        assert meta["user_id"] == "U08HWT0C6K1"
        assert meta["username"] == "eias"
        assert meta["observation_tokens"] == 50
        assert meta["total_sessions_observed"] == 3
        assert meta["reflection_count"] == 0
        assert "last_observed_at" in meta
        assert "created_at" in meta

    def test_from_meta_dict_roundtrip(self, sample_record):
        meta = sample_record.to_meta_dict()
        restored = MemoryRecord.from_meta_dict(meta, sample_record.observations)

        assert restored.user_id == sample_record.user_id
        assert restored.username == sample_record.username
        assert restored.observations == sample_record.observations
        assert restored.observation_tokens == sample_record.observation_tokens
        assert restored.total_sessions_observed == sample_record.total_sessions_observed
        assert restored.reflection_count == sample_record.reflection_count

    def test_from_meta_dict_missing_optional_fields(self):
        """선택 필드가 없어도 복원 가능"""
        data = {"user_id": "U12345"}
        record = MemoryRecord.from_meta_dict(data)
        assert record.user_id == "U12345"
        assert record.username == ""
        assert record.observation_tokens == 0
        assert record.last_observed_at is None

    def test_default_created_at(self):
        """created_at 기본값은 현재 시각"""
        record = MemoryRecord(user_id="U12345")
        assert record.created_at is not None
        assert isinstance(record.created_at, datetime)


class TestMemoryStoreGetSave:
    def test_get_nonexistent_record(self, store):
        result = store.get_record("NONEXISTENT")
        assert result is None

    def test_save_and_get_record(self, store, sample_record):
        store.save_record(sample_record)
        loaded = store.get_record(sample_record.user_id)

        assert loaded is not None
        assert loaded.user_id == sample_record.user_id
        assert loaded.username == sample_record.username
        assert loaded.observations == sample_record.observations
        assert loaded.observation_tokens == sample_record.observation_tokens
        assert loaded.total_sessions_observed == sample_record.total_sessions_observed

    def test_save_creates_directories(self, tmp_path):
        """존재하지 않는 디렉토리도 자동 생성"""
        deep_path = tmp_path / "a" / "b" / "c"
        store = MemoryStore(base_dir=deep_path)
        record = MemoryRecord(user_id="U12345", observations="test")
        store.save_record(record)

        assert store.observations_dir.exists()
        assert store.conversations_dir.exists()

    def test_overwrite_record(self, store, sample_record):
        store.save_record(sample_record)

        # 관찰 로그 갱신
        sample_record.observations = "## Updated observations"
        sample_record.observation_tokens = 10
        sample_record.total_sessions_observed = 4
        store.save_record(sample_record)

        loaded = store.get_record(sample_record.user_id)
        assert loaded.observations == "## Updated observations"
        assert loaded.observation_tokens == 10
        assert loaded.total_sessions_observed == 4

    def test_multiple_users(self, store):
        """여러 사용자의 레코드를 독립적으로 저장/로드"""
        record_a = MemoryRecord(user_id="UA", observations="User A observations")
        record_b = MemoryRecord(user_id="UB", observations="User B observations")

        store.save_record(record_a)
        store.save_record(record_b)

        loaded_a = store.get_record("UA")
        loaded_b = store.get_record("UB")

        assert loaded_a.observations == "User A observations"
        assert loaded_b.observations == "User B observations"


class TestMemoryStoreConversation:
    def test_save_and_load_conversation(self, store):
        messages = [
            {"role": "user", "content": "안녕하세요", "timestamp": "2026-02-10T09:00:00Z"},
            {"role": "assistant", "content": "안녕하세요, 서소영입니다.", "timestamp": "2026-02-10T09:00:01Z"},
        ]

        store.save_conversation("1234567890.123456", messages)
        loaded = store.load_conversation("1234567890.123456")

        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0]["role"] == "user"
        assert loaded[1]["content"] == "안녕하세요, 서소영입니다."

    def test_load_nonexistent_conversation(self, store):
        result = store.load_conversation("NONEXISTENT")
        assert result is None

    def test_conversation_preserves_unicode(self, store):
        """한글/이모지가 올바르게 저장/로드되는지 확인"""
        messages = [
            {"role": "user", "content": "🔴 캐릭터 설정을 수정해줘"},
        ]
        store.save_conversation("ts_unicode", messages)
        loaded = store.load_conversation("ts_unicode")

        assert loaded[0]["content"] == "🔴 캐릭터 설정을 수정해줘"
