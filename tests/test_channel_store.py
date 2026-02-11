"""ChannelStore 단위 테스트"""

import json

import pytest

from seosoyoung.memory.channel_store import ChannelStore


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


class TestChannelBuffer:
    """채널 루트 메시지 버퍼 테스트"""

    def test_append_and_load_channel_message(self, store):
        msg = {"ts": "1234.5678", "user": "U001", "text": "안녕하세요"}
        store.append_channel_message("C001", msg)

        loaded = store.load_channel_buffer("C001")
        assert len(loaded) == 1
        assert loaded[0]["text"] == "안녕하세요"

    def test_append_accumulates(self, store):
        store.append_channel_message("C001", {"ts": "1", "user": "U001", "text": "첫 번째"})
        store.append_channel_message("C001", {"ts": "2", "user": "U002", "text": "두 번째"})

        loaded = store.load_channel_buffer("C001")
        assert len(loaded) == 2

    def test_load_empty_buffer(self, store):
        assert store.load_channel_buffer("NONEXISTENT") == []

    def test_preserves_unicode(self, store):
        msg = {"ts": "1", "user": "U001", "text": "이모지 테스트 🔥"}
        store.append_channel_message("C001", msg)
        loaded = store.load_channel_buffer("C001")
        assert loaded[0]["text"] == "이모지 테스트 🔥"

    def test_independent_per_channel(self, store):
        store.append_channel_message("C001", {"ts": "1", "user": "U001", "text": "A"})
        store.append_channel_message("C002", {"ts": "2", "user": "U002", "text": "B"})

        assert store.load_channel_buffer("C001")[0]["text"] == "A"
        assert store.load_channel_buffer("C002")[0]["text"] == "B"


class TestThreadBuffer:
    """스레드 메시지 버퍼 테스트"""

    def test_append_and_load_thread_message(self, store):
        msg = {"ts": "1234.9999", "user": "U001", "text": "스레드 메시지", "thread_ts": "1234.5678"}
        store.append_thread_message("C001", "1234.5678", msg)

        loaded = store.load_thread_buffer("C001", "1234.5678")
        assert len(loaded) == 1
        assert loaded[0]["text"] == "스레드 메시지"

    def test_thread_accumulates(self, store):
        store.append_thread_message("C001", "1234.5678", {"ts": "1", "user": "U001", "text": "첫째"})
        store.append_thread_message("C001", "1234.5678", {"ts": "2", "user": "U002", "text": "둘째"})

        loaded = store.load_thread_buffer("C001", "1234.5678")
        assert len(loaded) == 2

    def test_load_empty_thread_buffer(self, store):
        assert store.load_thread_buffer("C001", "NONEXISTENT") == []

    def test_independent_per_thread(self, store):
        store.append_thread_message("C001", "ts_a", {"ts": "1", "user": "U001", "text": "A"})
        store.append_thread_message("C001", "ts_b", {"ts": "2", "user": "U002", "text": "B"})

        assert store.load_thread_buffer("C001", "ts_a")[0]["text"] == "A"
        assert store.load_thread_buffer("C001", "ts_b")[0]["text"] == "B"

    def test_load_all_thread_buffers(self, store):
        store.append_thread_message("C001", "ts_a", {"ts": "1", "user": "U001", "text": "A1"})
        store.append_thread_message("C001", "ts_a", {"ts": "2", "user": "U001", "text": "A2"})
        store.append_thread_message("C001", "ts_b", {"ts": "3", "user": "U002", "text": "B1"})

        all_threads = store.load_all_thread_buffers("C001")
        assert "ts_a" in all_threads
        assert "ts_b" in all_threads
        assert len(all_threads["ts_a"]) == 2
        assert len(all_threads["ts_b"]) == 1

    def test_load_all_thread_buffers_empty(self, store):
        assert store.load_all_thread_buffers("NONEXISTENT") == {}


class TestTokenCounting:
    """토큰 카운팅 테스트"""

    def test_count_buffer_tokens_empty(self, store):
        assert store.count_buffer_tokens("NONEXISTENT") == 0

    def test_count_buffer_tokens_with_data(self, store):
        store.append_channel_message("C001", {"ts": "1", "user": "U001", "text": "이것은 테스트 메시지입니다."})
        store.append_thread_message("C001", "ts_a", {"ts": "2", "user": "U001", "text": "스레드 메시지입니다."})

        token_count = store.count_buffer_tokens("C001")
        assert token_count > 0

    def test_count_includes_channel_and_threads(self, store):
        store.append_channel_message("C001", {"ts": "1", "user": "U001", "text": "채널 메시지"})
        channel_only = store.count_buffer_tokens("C001")

        store.append_thread_message("C001", "ts_a", {"ts": "2", "user": "U001", "text": "스레드 메시지"})
        with_thread = store.count_buffer_tokens("C001")

        assert with_thread > channel_only


class TestClearBuffers:
    """버퍼 비우기 테스트"""

    def test_clear_buffers(self, store):
        store.append_channel_message("C001", {"ts": "1", "user": "U001", "text": "채널"})
        store.append_thread_message("C001", "ts_a", {"ts": "2", "user": "U001", "text": "스레드"})

        store.clear_buffers("C001")

        assert store.load_channel_buffer("C001") == []
        assert store.load_thread_buffer("C001", "ts_a") == []
        assert store.count_buffer_tokens("C001") == 0

    def test_clear_nonexistent_buffers(self, store):
        """존재하지 않는 채널 버퍼 비우기도 에러 없음"""
        store.clear_buffers("NONEXISTENT")


class TestDigest:
    """digest.md CRUD 테스트"""

    def test_get_digest_empty(self, store):
        assert store.get_digest("NONEXISTENT") is None

    def test_save_and_get_digest(self, store):
        content = "## 채널 관찰 요약\n\n- 오늘은 조용한 하루였다."
        meta = {"last_digested_at": "2026-02-11T10:00:00Z", "total_digests": 1}
        store.save_digest("C001", content, meta)

        result = store.get_digest("C001")
        assert result is not None
        assert result["content"] == content
        assert result["meta"]["total_digests"] == 1

    def test_save_digest_overwrites(self, store):
        store.save_digest("C001", "첫 번째 요약", {"total_digests": 1})
        store.save_digest("C001", "두 번째 요약", {"total_digests": 2})

        result = store.get_digest("C001")
        assert result["content"] == "두 번째 요약"
        assert result["meta"]["total_digests"] == 2

    def test_digest_preserves_unicode(self, store):
        content = "🔥 채널에서 열띤 토론이 벌어졌다"
        store.save_digest("C001", content, {})

        result = store.get_digest("C001")
        assert result["content"] == content

    def test_digest_independent_per_channel(self, store):
        store.save_digest("C001", "채널1 요약", {})
        store.save_digest("C002", "채널2 요약", {})

        assert store.get_digest("C001")["content"] == "채널1 요약"
        assert store.get_digest("C002")["content"] == "채널2 요약"

    def test_creates_directory(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c"
        store = ChannelStore(base_dir=deep_path)
        store.save_digest("C001", "test", {})
        assert store.get_digest("C001")["content"] == "test"
