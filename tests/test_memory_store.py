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
        thread_ts="1234567890.123456",
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
        assert meta["thread_ts"] == "1234567890.123456"
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

        assert restored.thread_ts == sample_record.thread_ts
        assert restored.user_id == sample_record.user_id
        assert restored.username == sample_record.username
        assert restored.observations == sample_record.observations
        assert restored.observation_tokens == sample_record.observation_tokens
        assert restored.total_sessions_observed == sample_record.total_sessions_observed
        assert restored.reflection_count == sample_record.reflection_count

    def test_from_meta_dict_missing_optional_fields(self):
        """선택 필드가 없어도 복원 가능"""
        data = {"thread_ts": "1234.5678"}
        record = MemoryRecord.from_meta_dict(data)
        assert record.thread_ts == "1234.5678"
        assert record.user_id == ""
        assert record.username == ""
        assert record.observation_tokens == 0
        assert record.last_observed_at is None

    def test_default_created_at(self):
        """created_at 기본값은 현재 시각"""
        record = MemoryRecord(thread_ts="1234.5678")
        assert record.created_at is not None
        assert isinstance(record.created_at, datetime)


class TestMemoryStoreGetSave:
    def test_get_nonexistent_record(self, store):
        result = store.get_record("NONEXISTENT")
        assert result is None

    def test_save_and_get_record(self, store, sample_record):
        store.save_record(sample_record)
        loaded = store.get_record(sample_record.thread_ts)

        assert loaded is not None
        assert loaded.thread_ts == sample_record.thread_ts
        assert loaded.user_id == sample_record.user_id
        assert loaded.username == sample_record.username
        assert loaded.observations == sample_record.observations
        assert loaded.observation_tokens == sample_record.observation_tokens
        assert loaded.total_sessions_observed == sample_record.total_sessions_observed

    def test_save_creates_directories(self, tmp_path):
        """존재하지 않는 디렉토리도 자동 생성"""
        deep_path = tmp_path / "a" / "b" / "c"
        store = MemoryStore(base_dir=deep_path)
        record = MemoryRecord(thread_ts="1234.5678", observations="test")
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

        loaded = store.get_record(sample_record.thread_ts)
        assert loaded.observations == "## Updated observations"
        assert loaded.observation_tokens == 10
        assert loaded.total_sessions_observed == 4

    def test_multiple_sessions(self, store):
        """여러 세션의 레코드를 독립적으로 저장/로드"""
        record_a = MemoryRecord(
            thread_ts="ts_a", user_id="UA", observations="Session A observations"
        )
        record_b = MemoryRecord(
            thread_ts="ts_b", user_id="UB", observations="Session B observations"
        )

        store.save_record(record_a)
        store.save_record(record_b)

        loaded_a = store.get_record("ts_a")
        loaded_b = store.get_record("ts_b")

        assert loaded_a.observations == "Session A observations"
        assert loaded_b.observations == "Session B observations"


class TestMemoryStorePending:
    def test_append_and_load_pending(self, store):
        """pending 메시지 누적 및 로드"""
        messages1 = [{"role": "user", "content": "첫 번째 대화"}]
        messages2 = [{"role": "user", "content": "두 번째 대화"}]

        store.append_pending_messages("ts_1234", messages1)
        store.append_pending_messages("ts_1234", messages2)

        loaded = store.load_pending_messages("ts_1234")
        assert len(loaded) == 2
        assert loaded[0]["content"] == "첫 번째 대화"
        assert loaded[1]["content"] == "두 번째 대화"

    def test_load_empty_pending(self, store):
        """pending이 없으면 빈 리스트"""
        assert store.load_pending_messages("NONEXISTENT") == []

    def test_clear_pending(self, store):
        """pending 비우기"""
        store.append_pending_messages("ts_1234", [{"role": "user", "content": "test"}])
        assert len(store.load_pending_messages("ts_1234")) == 1

        store.clear_pending_messages("ts_1234")
        assert store.load_pending_messages("ts_1234") == []

    def test_clear_nonexistent_pending(self, store):
        """존재하지 않는 pending 비우기는 에러 없음"""
        store.clear_pending_messages("NONEXISTENT")

    def test_pending_preserves_unicode(self, store):
        """한글/이모지가 올바르게 저장/로드"""
        messages = [{"role": "user", "content": "🔴 캐릭터 정보 요청"}]
        store.append_pending_messages("ts_1234", messages)

        loaded = store.load_pending_messages("ts_1234")
        assert loaded[0]["content"] == "🔴 캐릭터 정보 요청"

    def test_pending_independent_per_session(self, store):
        """세션별 pending은 독립적"""
        store.append_pending_messages("ts_a", [{"role": "user", "content": "A"}])
        store.append_pending_messages("ts_b", [{"role": "user", "content": "B"}])

        assert store.load_pending_messages("ts_a")[0]["content"] == "A"
        assert store.load_pending_messages("ts_b")[0]["content"] == "B"

    def test_pending_creates_directory(self, tmp_path):
        """pending 디렉토리 자동 생성"""
        deep_path = tmp_path / "x" / "y"
        store = MemoryStore(base_dir=deep_path)
        store.append_pending_messages("ts_1234", [{"role": "user", "content": "test"}])
        assert store.pending_dir.exists()


class TestMemoryStoreInjectFlag:
    def test_set_and_check_flag(self, store):
        """플래그 설정 후 확인하면 True, 다시 확인하면 False"""
        store.set_inject_flag("ts_1234")
        assert store.check_and_clear_inject_flag("ts_1234") is True
        assert store.check_and_clear_inject_flag("ts_1234") is False

    def test_check_nonexistent_flag(self, store):
        """플래그 없으면 False"""
        assert store.check_and_clear_inject_flag("NONEXISTENT") is False

    def test_flag_independent_per_session(self, store):
        """세션별 플래그는 독립적"""
        store.set_inject_flag("ts_a")
        assert store.check_and_clear_inject_flag("ts_a") is True
        assert store.check_and_clear_inject_flag("ts_b") is False

    def test_flag_creates_directory(self, tmp_path):
        """디렉토리 자동 생성"""
        deep_path = tmp_path / "deep" / "path"
        store = MemoryStore(base_dir=deep_path)
        store.set_inject_flag("ts_1234")
        assert store.check_and_clear_inject_flag("ts_1234") is True

    def test_set_flag_idempotent(self, store):
        """플래그 중복 설정해도 문제 없음"""
        store.set_inject_flag("ts_1234")
        store.set_inject_flag("ts_1234")
        assert store.check_and_clear_inject_flag("ts_1234") is True
        assert store.check_and_clear_inject_flag("ts_1234") is False


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
