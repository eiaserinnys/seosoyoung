"""OpenAI 임베딩 캐시 테스트."""

import json
import hashlib
import pytest
from unittest.mock import patch, MagicMock

from seosoyoung.search.embedding_cache import EmbeddingCache


class TestEmbeddingCache:
    """EmbeddingCache 테스트."""

    @pytest.fixture
    def cache_path(self, tmp_path):
        return tmp_path / "embedding_cache.json"

    @pytest.fixture
    def cache(self, cache_path):
        return EmbeddingCache(cache_path=cache_path, api_key="test-key")

    def test_text_hash(self, cache):
        h = cache._hash_text("hello")
        expected = hashlib.sha256("hello".encode()).hexdigest()
        assert h == expected

    def test_cache_miss_calls_api(self, cache):
        fake_vector = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=fake_vector)]

        with patch.object(cache._client.embeddings, "create", return_value=mock_response) as mock_create:
            result = cache.get_embeddings(["hello world"])
            mock_create.assert_called_once()
            assert len(result) == 1
            assert result[0] == fake_vector

    def test_cache_hit_skips_api(self, cache, cache_path):
        fake_vector = [0.2] * 1536
        text = "cached text"
        h = hashlib.sha256(text.encode()).hexdigest()

        # 미리 캐시 파일 생성
        cache_data = {h: fake_vector}
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

        cache_fresh = EmbeddingCache(cache_path=cache_path, api_key="test-key")

        with patch.object(cache_fresh._client.embeddings, "create") as mock_create:
            result = cache_fresh.get_embeddings([text])
            mock_create.assert_not_called()
            assert result[0] == fake_vector

    def test_mixed_cache_hit_and_miss(self, cache):
        cached_text = "already cached"
        new_text = "not cached"
        cached_hash = cache._hash_text(cached_text)
        cached_vector = [0.3] * 1536
        new_vector = [0.4] * 1536

        cache._cache[cached_hash] = cached_vector

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=new_vector)]

        with patch.object(cache._client.embeddings, "create", return_value=mock_response) as mock_create:
            result = cache.get_embeddings([cached_text, new_text])

            # API는 미캐시 1건만 호출
            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert len(call_args.kwargs.get("input", call_args[1].get("input", []))) == 1

            assert result[0] == cached_vector
            assert result[1] == new_vector

    def test_saves_to_file(self, cache, cache_path):
        fake_vector = [0.5] * 1536
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=fake_vector)]

        with patch.object(cache._client.embeddings, "create", return_value=mock_response):
            cache.get_embeddings(["save test"])
            cache.save()

        assert cache_path.exists()
        with open(cache_path) as f:
            data = json.load(f)
        assert len(data) == 1

    def test_batch_processing(self, cache):
        """배치 크기를 초과하는 입력이 여러 번 API를 호출하는지 확인."""
        texts = [f"text_{i}" for i in range(5)]
        fake_vector = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=fake_vector)]

        with patch.object(cache._client.embeddings, "create", return_value=mock_response) as mock_create:
            # batch_size=2로 테스트
            cache._batch_size = 2
            mock_response.data = [MagicMock(embedding=fake_vector)] * 2

            # 5개 텍스트 → 3번 호출 (2+2+1)
            result = cache.get_embeddings(texts)
            assert mock_create.call_count == 3
            assert len(result) == 5

    def test_empty_input(self, cache):
        result = cache.get_embeddings([])
        assert result == []

    def test_stats(self, cache):
        cached_hash = cache._hash_text("cached")
        cache._cache[cached_hash] = [0.1] * 1536

        stats = cache.get_stats()
        assert stats["cached_entries"] == 1
        assert "cache_path" in stats
