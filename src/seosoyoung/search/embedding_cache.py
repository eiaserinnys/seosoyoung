"""OpenAI 임베딩 캐시.

텍스트 → 임베딩 벡터 변환 시 SHA256 해시 기반 로컬 캐시를 사용하여
중복 API 호출을 방지한다.
"""

import hashlib
import json
from pathlib import Path

from openai import OpenAI


class EmbeddingCache:
    """OpenAI text-embedding-3-small 임베딩 + 로컬 JSON 캐시."""

    def __init__(
        self,
        cache_path: str | Path,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        batch_size: int = 2048,
    ):
        self._cache_path = Path(cache_path)
        self._model = model
        self._batch_size = batch_size
        self._client = OpenAI(api_key=api_key)
        self._cache: dict[str, list[float]] = {}
        self._load()

    def _load(self):
        """캐시 파일 로드."""
        if self._cache_path.exists():
            with open(self._cache_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)

    def save(self):
        """캐시 파일 저장."""
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)

    @staticmethod
    def _hash_text(text: str) -> str:
        """텍스트의 SHA256 해시."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트에 대한 임베딩 벡터 반환.

        캐시 히트 시 API를 호출하지 않고, 미스 시에만 배치로 API를 호출한다.

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            각 텍스트에 대응하는 임베딩 벡터 리스트 (입력 순서 유지)
        """
        if not texts:
            return []

        # 해시 계산 및 캐시 확인
        hashes = [self._hash_text(t) for t in texts]
        results: list[list[float] | None] = [None] * len(texts)

        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, (h, text) in enumerate(zip(hashes, texts)):
            if h in self._cache:
                results[i] = self._cache[h]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # 미캐시 텍스트를 배치로 API 호출
        if uncached_texts:
            embeddings = self._call_api_batched(uncached_texts)
            for idx, emb in zip(uncached_indices, embeddings):
                h = hashes[idx]
                self._cache[h] = emb
                results[idx] = emb

        return results  # type: ignore[return-value]

    def _call_api_batched(self, texts: list[str]) -> list[list[float]]:
        """배치 단위로 OpenAI API 호출."""
        all_embeddings: list[list[float]] = []

        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._client.embeddings.create(
                model=self._model,
                input=batch,
            )
            all_embeddings.extend(d.embedding for d in response.data)

        return all_embeddings

    def get_stats(self) -> dict:
        """캐시 통계."""
        return {
            "cached_entries": len(self._cache),
            "cache_path": str(self._cache_path),
        }
