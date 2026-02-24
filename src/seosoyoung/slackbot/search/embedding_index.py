"""임베딩 인덱스 빌더 + 코사인 유사도 검색.

A-RAG 방식: 문장 단위 임베딩 생성 → 검색 시 부모 청크(dlgId/chunk_id) 기준 집계.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from .embedding_cache import EmbeddingCache
from .sentence_splitter import split_sentences

# 로어 인덱서와 동일한 스킵 파일
_SKIP_FILES = {"actor_code.yaml"}


def _section_text(section_data: dict) -> tuple[str, str]:
    """섹션 dict에서 kr/en 텍스트 추출 (lore_indexer와 동일 로직)."""
    kr_raw = section_data.get("kr", "")
    en_raw = section_data.get("en", "")

    if isinstance(kr_raw, list):
        kr = "\n".join(str(v) for v in kr_raw)
    else:
        kr = str(kr_raw) if kr_raw else ""

    if isinstance(en_raw, list):
        en = "\n".join(str(v) for v in en_raw)
    else:
        en = str(en_raw) if en_raw else ""

    return kr.strip(), en.strip()


def _is_content_section(key: str, value) -> bool:
    """kr/en 텍스트를 포함하는 콘텐츠 섹션인지."""
    if key.startswith("_") or not isinstance(value, dict):
        return False
    return "kr" in value or "en" in value


class EmbeddingIndexBuilder:
    """dlglist 대사와 eb_lore 텍스트를 문장 단위 임베딩 인덱스로 빌드."""

    def __init__(
        self,
        narrative_path: str | Path | None,
        lore_path: str | Path | None,
        output_dir: str | Path,
        cache_path: str | Path | None = None,
        api_key: str | None = None,
    ):
        self._narrative_path = Path(narrative_path) if narrative_path else None
        self._lore_path = Path(lore_path) if lore_path else None
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if cache_path is None:
            cache_path = self._output_dir / "embedding_cache.json"
        self._cache = EmbeddingCache(cache_path=cache_path, api_key=api_key)

    def build_dialogue_index(self) -> dict:
        """dlglist 대사를 문장 분할 → 임베딩 인덱스 생성."""
        if not self._narrative_path:
            raise ValueError("narrative_path is required for dialogue index")

        dlglist_path = self._narrative_path / "narrative" / "dlglist"
        if not dlglist_path.exists():
            raise FileNotFoundError(f"dlglist not found: {dlglist_path}")

        sentences: list[str] = []
        metadata: list[dict] = []
        total_dialogues = 0

        for yaml_file in sorted(dlglist_path.glob("*.yaml")):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "dialogues" not in data:
                continue

            for dlg in data["dialogues"]:
                dlg_id = dlg.get("dlgId", "")
                if not dlg_id:
                    continue

                total_dialogues += 1
                speaker = dlg.get("speaker", "")

                for lang, key in [("kr", "kr"), ("en", "en")]:
                    text = dlg.get(key, "")
                    if not text:
                        continue

                    for sent in split_sentences(text):
                        sentences.append(sent)
                        metadata.append(
                            {
                                "chunk_id": dlg_id,
                                "text": sent,
                                "source_type": "dialogue",
                                "lang": lang,
                                "speaker": speaker,
                                "source_file": yaml_file.name,
                            }
                        )

        vectors = self._embed_sentences(sentences)

        self._save_index(vectors, metadata, "dialogue")
        self._save_build_info(
            "dialogue",
            {
                "total_sentences": len(sentences),
                "total_dialogues": total_dialogues,
            },
        )
        self._cache.save()

        return {
            "total_sentences": len(sentences),
            "total_dialogues": total_dialogues,
        }

    def build_lore_index(self) -> dict:
        """eb_lore 텍스트를 문장 분할 → 임베딩 인덱스 생성."""
        if not self._lore_path:
            raise ValueError("lore_path is required for lore index")

        content_path = self._lore_path / "content"

        sentences: list[str] = []
        metadata: list[dict] = []
        total_chunks = 0

        # characters
        chars_path = content_path / "characters"
        if chars_path.exists():
            for yaml_file in sorted(chars_path.glob("*.yaml")):
                if yaml_file.name in _SKIP_FILES:
                    continue
                n = self._index_entity(
                    yaml_file, "character", sentences, metadata
                )
                total_chunks += n

        # glossary
        glossary_file = content_path / "glossary.yaml"
        if glossary_file.exists():
            n = self._index_glossary(glossary_file, sentences, metadata)
            total_chunks += n

        # places
        places_path = content_path / "places"
        if places_path.exists():
            for yaml_file in sorted(places_path.glob("*.yaml")):
                n = self._index_entity(
                    yaml_file, "place", sentences, metadata
                )
                total_chunks += n

        # synopsis
        synopsis_path = content_path / "synopsis"
        if synopsis_path.exists():
            for yaml_file in sorted(synopsis_path.glob("*.yaml")):
                n = self._index_entity(
                    yaml_file, "synopsis", sentences, metadata
                )
                total_chunks += n

        vectors = self._embed_sentences(sentences)

        self._save_index(vectors, metadata, "lore")
        self._save_build_info(
            "lore",
            {
                "total_sentences": len(sentences),
                "total_chunks": total_chunks,
            },
        )
        self._cache.save()

        return {
            "total_sentences": len(sentences),
            "total_chunks": total_chunks,
        }

    def _index_entity(
        self,
        yaml_file: Path,
        source_type: str,
        sentences: list[str],
        metadata: list[dict],
    ) -> int:
        """캐릭터/장소/시놉시스 YAML → 문장 분할."""
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return 0

        entity_id = data.get("id", yaml_file.stem)

        if source_type == "character":
            prefix = f"char:{entity_id}"
        elif source_type == "place":
            prefix = f"place:{entity_id}"
        else:
            prefix = f"synopsis:{entity_id}"

        count = 0
        for key, value in data.items():
            if not _is_content_section(key, value):
                continue
            if key in ("name", "title", "id"):
                continue

            text_kr, text_en = _section_text(value)
            chunk_id = f"{prefix}:{key}"

            for lang, text in [("kr", text_kr), ("en", text_en)]:
                if not text:
                    continue
                for sent in split_sentences(text):
                    sentences.append(sent)
                    metadata.append(
                        {
                            "chunk_id": chunk_id,
                            "text": sent,
                            "source_type": source_type,
                            "lang": lang,
                            "source_id": entity_id,
                            "section": key,
                        }
                    )
            if text_kr or text_en:
                count += 1

        return count

    def _index_glossary(
        self,
        glossary_file: Path,
        sentences: list[str],
        metadata: list[dict],
    ) -> int:
        """용어집 YAML → 문장 분할."""
        with open(glossary_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return 0

        count = 0
        for category_key, category_data in data.items():
            if not isinstance(category_data, dict):
                continue
            items = category_data.get("items")
            if not isinstance(items, list):
                continue

            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue

                name_data = item.get("name", {})
                desc_data = item.get("description", {})

                chunk_id = f"glossary:{category_key}:{idx}"

                for lang in ("kr", "en"):
                    name = ""
                    desc = ""
                    if isinstance(name_data, dict):
                        name = str(name_data.get(lang, ""))
                    if isinstance(desc_data, dict):
                        desc = str(desc_data.get(lang, ""))

                    combined = f"{name}\n{desc}".strip()
                    if not combined:
                        continue

                    for sent in split_sentences(combined):
                        sentences.append(sent)
                        metadata.append(
                            {
                                "chunk_id": chunk_id,
                                "text": sent,
                                "source_type": "glossary",
                                "lang": lang,
                                "source_id": "glossary",
                                "section": category_key,
                            }
                        )
                count += 1

        return count

    def _embed_sentences(self, sentences: list[str]) -> np.ndarray:
        """문장 리스트 → 임베딩 벡터 (numpy)."""
        if not sentences:
            return np.zeros((0, 1536), dtype=np.float32)

        embeddings = self._cache.get_embeddings(sentences)
        return np.array(embeddings, dtype=np.float32)

    def _save_index(
        self,
        vectors: np.ndarray,
        metadata: list[dict],
        prefix: str,
    ):
        """벡터 + 메타데이터를 파일로 저장."""
        np.save(self._output_dir / f"{prefix}_vectors.npy", vectors)
        with open(
            self._output_dir / f"{prefix}_metadata.json", "w", encoding="utf-8"
        ) as f:
            json.dump(metadata, f, ensure_ascii=False)

    def _save_build_info(self, prefix: str, stats: dict):
        """빌드 메타 정보 저장."""
        info = {
            "build_time": datetime.now(timezone.utc).isoformat(),
            **stats,
        }
        with open(
            self._output_dir / f"{prefix}_build_info.json", "w", encoding="utf-8"
        ) as f:
            json.dump(info, f, ensure_ascii=False, indent=2)


def load_embedding_index(
    index_dir: str | Path, prefix: str
) -> tuple[np.ndarray, list[dict]]:
    """저장된 임베딩 인덱스 로드.

    Args:
        index_dir: 인덱스 디렉토리
        prefix: 'dialogue' 또는 'lore'

    Returns:
        (vectors, metadata) 튜플
    """
    index_dir = Path(index_dir)
    vec_path = index_dir / f"{prefix}_vectors.npy"
    meta_path = index_dir / f"{prefix}_metadata.json"

    if not vec_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            f"Embedding index not found at {index_dir}/{prefix}_*"
        )

    vectors = np.load(vec_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return vectors, metadata


def cosine_similarity_search(
    query_vector: np.ndarray,
    vectors: np.ndarray,
    metadata: list[dict],
    top_k: int = 10,
    aggregate_by_chunk: bool = False,
) -> list[dict]:
    """코사인 유사도 기반 검색.

    Args:
        query_vector: 쿼리 벡터 (1D)
        vectors: 인덱스 벡터 (N x D)
        metadata: 각 벡터의 메타데이터
        top_k: 반환할 최대 결과 수
        aggregate_by_chunk: True면 chunk_id 기준 집계 (A-RAG 방식)

    Returns:
        검색 결과 리스트 (score 내림차순)
    """
    if vectors.shape[0] == 0:
        return []

    # 코사인 유사도: dot(q, v) / (||q|| * ||v||)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return []

    vec_norms = np.linalg.norm(vectors, axis=1)
    # 0-norm 벡터 방지
    vec_norms = np.where(vec_norms == 0, 1e-10, vec_norms)

    similarities = vectors @ query_vector / (vec_norms * query_norm)

    if aggregate_by_chunk:
        # A-RAG: 각 chunk의 최고 점수 문장으로 집계
        chunk_best: dict[str, tuple[float, int]] = {}
        for i, sim in enumerate(similarities):
            cid = metadata[i]["chunk_id"]
            if cid not in chunk_best or sim > chunk_best[cid][0]:
                chunk_best[cid] = (float(sim), i)

        sorted_chunks = sorted(
            chunk_best.items(), key=lambda x: x[1][0], reverse=True
        )[:top_k]

        results = []
        for cid, (score, best_idx) in sorted_chunks:
            entry = dict(metadata[best_idx])
            entry["score"] = score
            entry["best_sentence_idx"] = best_idx
            results.append(entry)
        return results
    else:
        # 문장 단위 결과
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            entry = dict(metadata[idx])
            entry["score"] = float(similarities[idx])
            results.append(entry)
        return results
