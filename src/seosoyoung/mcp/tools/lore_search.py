"""A-RAG 로어 검색 MCP 도구 — keyword_search, semantic_search, chunk_read.

Phase 1-2에서 구축한 Whoosh 인덱스 + 임베딩 인덱스를 활용하여
계층적 검색 인터페이스를 제공한다.
"""

import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import yaml
from whoosh.index import open_dir, exists_in
from whoosh.qparser import MultifieldParser
from whoosh.query import Term, And

from seosoyoung.slackbot.search.embedding_index import (
    cosine_similarity_search,
    load_embedding_index,
)
from seosoyoung.slackbot.search.embedding_cache import EmbeddingCache


# Context Tracker: 세션 내 이미 읽은 chunk_id 추적 (TTL 30분)
_CONTEXT_TRACKER_TTL = 30 * 60  # 30분

_context_tracker: dict[str, float] = {}  # chunk_id → last_access_timestamp


def _track_chunk(chunk_id: str) -> bool:
    """chunk_id를 추적하고, 이미 읽은 청크면 True 반환."""
    _gc_tracker()
    now = time.time()
    if chunk_id in _context_tracker:
        _context_tracker[chunk_id] = now
        return True
    _context_tracker[chunk_id] = now
    return False


def _gc_tracker():
    """TTL이 지난 항목 정리."""
    now = time.time()
    expired = [k for k, t in _context_tracker.items() if now - t > _CONTEXT_TRACKER_TTL]
    for k in expired:
        del _context_tracker[k]


def reset_context_tracker():
    """테스트용: 트래커 초기화."""
    _context_tracker.clear()


# Lazy-loaded 인덱스 싱글턴
_indices: dict[str, object] = {}


def _get_index_base_path() -> Path:
    """인덱스 기본 경로."""
    return Path.cwd() / ".local" / "index"


def _get_dialogue_searcher():
    """Whoosh 대사 인덱스 searcher (lazy load)."""
    if "dialogue_ix" not in _indices:
        idx_path = _get_index_base_path() / "dialogues"
        if not exists_in(str(idx_path)):
            raise FileNotFoundError(f"Dialogue index not found: {idx_path}")
        _indices["dialogue_ix"] = open_dir(str(idx_path))
    return _indices["dialogue_ix"]


def _get_lore_searcher():
    """Whoosh 로어 인덱스 (lazy load)."""
    if "lore_ix" not in _indices:
        idx_path = _get_index_base_path() / "lore"
        if not exists_in(str(idx_path)):
            raise FileNotFoundError(f"Lore index not found: {idx_path}")
        _indices["lore_ix"] = open_dir(str(idx_path))
    return _indices["lore_ix"]


def _get_embedding_data(prefix: str) -> tuple[np.ndarray, list[dict]]:
    """임베딩 벡터 + 메타데이터 (lazy load)."""
    key = f"emb_{prefix}"
    if key not in _indices:
        idx_dir = _get_index_base_path() / "embeddings"
        _indices[key] = load_embedding_index(idx_dir, prefix)
    return _indices[key]


def _get_embedding_cache() -> EmbeddingCache:
    """임베딩 캐시 (쿼리 임베딩용, lazy load)."""
    if "emb_cache" not in _indices:
        cache_path = _get_index_base_path() / "embeddings" / "embedding_cache.json"
        _indices["emb_cache"] = EmbeddingCache(cache_path=cache_path)
    return _indices["emb_cache"]


def reset_indices():
    """테스트용: 인덱스 캐시 초기화."""
    _indices.clear()


def lore_keyword_search(
    keywords: list[str],
    speaker: Optional[str] = None,
    source: str = "all",
    top_k: int = 10,
) -> dict:
    """키워드 기반 로어/대사 검색.

    Whoosh 인덱스에서 키워드를 검색하여 chunk_id + 매칭 스니펫을 반환한다.

    Args:
        keywords: 검색 키워드 리스트
        speaker: 화자 필터 (대사 전용, 예: fx, ar)
        source: 검색 대상 — "dlg" (대사), "lore" (설정), "all" (전체)
        top_k: 최대 결과 수

    Returns:
        검색 결과 dict
    """
    query_text = " ".join(keywords)
    results = []

    if source in ("dlg", "all"):
        try:
            dlg_results = _search_dialogue_whoosh(query_text, speaker, top_k)
            results.extend(dlg_results)
        except FileNotFoundError:
            pass

    if source in ("lore", "all"):
        try:
            lore_results = _search_lore_whoosh(query_text, top_k)
            results.extend(lore_results)
        except FileNotFoundError:
            pass

    # 점수 기준 정렬 후 top_k
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_k]

    return {
        "query": query_text,
        "source": source,
        "count": len(results),
        "results": results,
    }


def _search_dialogue_whoosh(
    query_text: str, speaker: Optional[str], top_k: int
) -> list[dict]:
    """Whoosh 대사 인덱스 검색."""
    ix = _get_dialogue_searcher()
    with ix.searcher() as searcher:
        mparser = MultifieldParser(["text_kr", "text_en"], ix.schema)
        q = mparser.parse(query_text)

        if speaker:
            q = And([q, Term("speaker", speaker.lower())])

        whoosh_results = searcher.search(q, limit=top_k)

        out = []
        for r in whoosh_results:
            # 스니펫: 한국어 텍스트 앞 100자
            text_kr = r["text_kr"]
            snippet = text_kr[:100].strip() + ("..." if len(text_kr) > 100 else "")

            out.append({
                "chunk_id": r["dlgId"],
                "source_type": "dialogue",
                "speaker": r["speaker"],
                "snippet": snippet,
                "score": r.score,
            })
        return out


def _search_lore_whoosh(query_text: str, top_k: int) -> list[dict]:
    """Whoosh 로어 인덱스 검색."""
    ix = _get_lore_searcher()
    with ix.searcher() as searcher:
        mparser = MultifieldParser(
            ["text_kr", "text_en", "name_kr", "name_en"], ix.schema
        )
        q = mparser.parse(query_text)
        whoosh_results = searcher.search(q, limit=top_k)

        out = []
        for r in whoosh_results:
            text_kr = r.get("text_kr", "")
            snippet = text_kr[:100].strip() + ("..." if len(text_kr) > 100 else "")

            out.append({
                "chunk_id": r["chunk_id"],
                "source_type": r["source_type"],
                "section": r.get("section", ""),
                "name_kr": r.get("name_kr", ""),
                "snippet": snippet,
                "score": r.score,
            })
        return out


def lore_semantic_search(
    query: str,
    speaker: Optional[str] = None,
    source: str = "all",
    top_k: int = 10,
) -> dict:
    """의미 기반 로어/대사 검색.

    쿼리를 임베딩 벡터로 변환 후 코사인 유사도로 검색한다.
    A-RAG 방식으로 부모 청크 기준 집계.

    Args:
        query: 검색 쿼리 텍스트
        speaker: 화자 필터 (대사 전용)
        source: 검색 대상 — "dlg", "lore", "all"
        top_k: 최대 결과 수

    Returns:
        검색 결과 dict
    """
    # 쿼리 임베딩
    cache = _get_embedding_cache()
    query_emb = cache.get_embeddings([query])[0]
    query_vec = np.array(query_emb, dtype=np.float32)

    results = []

    if source in ("dlg", "all"):
        try:
            vectors, metadata = _get_embedding_data("dialogue")
            # speaker 필터
            if speaker:
                filtered_indices = [
                    i for i, m in enumerate(metadata)
                    if m.get("speaker", "").lower() == speaker.lower()
                ]
                if filtered_indices:
                    f_vectors = vectors[filtered_indices]
                    f_metadata = [metadata[i] for i in filtered_indices]
                    dlg_results = cosine_similarity_search(
                        query_vec, f_vectors, f_metadata,
                        top_k=top_k, aggregate_by_chunk=True,
                    )
                else:
                    dlg_results = []
            else:
                dlg_results = cosine_similarity_search(
                    query_vec, vectors, metadata,
                    top_k=top_k, aggregate_by_chunk=True,
                )
            for r in dlg_results:
                results.append({
                    "chunk_id": r["chunk_id"],
                    "source_type": "dialogue",
                    "speaker": r.get("speaker", ""),
                    "snippet": r.get("text", "")[:100],
                    "score": r["score"],
                })
        except FileNotFoundError:
            pass

    if source in ("lore", "all"):
        try:
            vectors, metadata = _get_embedding_data("lore")
            lore_results = cosine_similarity_search(
                query_vec, vectors, metadata,
                top_k=top_k, aggregate_by_chunk=True,
            )
            for r in lore_results:
                results.append({
                    "chunk_id": r["chunk_id"],
                    "source_type": r.get("source_type", "lore"),
                    "section": r.get("section", ""),
                    "snippet": r.get("text", "")[:100],
                    "score": r["score"],
                })
        except FileNotFoundError:
            pass

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_k]

    return {
        "query": query,
        "source": source,
        "count": len(results),
        "results": results,
    }


def lore_chunk_read(
    chunk_id: str,
    include_adjacent: bool = False,
) -> dict:
    """chunk_id로 전체 텍스트를 읽는다.

    - dlg 청크 (dlgId): 한/영 전체 텍스트 반환
    - lore 청크 (char:fx:basic_info 등): 해당 YAML 섹션 전체 텍스트 반환
    - Context Tracker: 이미 읽은 청크는 간략 메시지만 반환 (토큰 절약)

    Args:
        chunk_id: 청크 ID (dlgId 또는 lore chunk_id)
        include_adjacent: True면 인접 대사/섹션도 포함

    Returns:
        청크 전체 텍스트 dict
    """
    # Context Tracker 확인
    already_read = _track_chunk(chunk_id)
    if already_read:
        return {
            "chunk_id": chunk_id,
            "already_read": True,
            "message": "이미 읽은 청크입니다. 다시 필요하면 context tracker를 초기화해주세요.",
        }

    # lore 청크인지 dlg 청크인지 판별
    if ":" in chunk_id:
        return _read_lore_chunk(chunk_id, include_adjacent)
    else:
        return _read_dialogue_chunk(chunk_id, include_adjacent)


def _read_dialogue_chunk(chunk_id: str, include_adjacent: bool) -> dict:
    """dlgId로 대사 전체 텍스트 읽기."""
    # Whoosh 인덱스에서 dlgId 조회
    ix = _get_dialogue_searcher()
    with ix.searcher() as searcher:
        results = searcher.search(Term("dlgId", chunk_id), limit=1)
        if not results:
            return {"chunk_id": chunk_id, "error": f"대사를 찾을 수 없습니다: {chunk_id}"}

        r = results[0]
        entry = {
            "chunk_id": chunk_id,
            "source_type": "dialogue",
            "speaker": r["speaker"],
            "text_kr": r["text_kr"],
            "text_en": r["text_en"],
            "labels": r.get("labels", ""),
            "revision": r.get("revision", ""),
            "acts": r.get("acts", ""),
            "trigger": r.get("trigger", ""),
            "source_file": r.get("source_file", ""),
        }

    # 인접 대사
    if include_adjacent:
        adjacent = _get_adjacent_dialogues(chunk_id, entry.get("source_file", ""))
        if adjacent:
            entry["adjacent"] = adjacent

    return entry


def _get_adjacent_dialogues(dlg_id: str, source_file: str) -> list[dict]:
    """같은 dlglist 파일에서 인접 대사를 가져온다."""
    if not source_file:
        return []

    dlglist_path = Path.cwd() / "eb_narrative" / "narrative" / "dlglist" / source_file
    if not dlglist_path.exists():
        return []

    try:
        with open(dlglist_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []

    if not data or "dialogues" not in data:
        return []

    dialogues = data["dialogues"]
    target_idx = None
    for i, dlg in enumerate(dialogues):
        if dlg.get("dlgId") == dlg_id:
            target_idx = i
            break

    if target_idx is None:
        return []

    adjacent = []
    for offset in [-2, -1, 1, 2]:
        adj_idx = target_idx + offset
        if 0 <= adj_idx < len(dialogues):
            dlg = dialogues[adj_idx]
            adjacent.append({
                "dlgId": dlg.get("dlgId", ""),
                "speaker": dlg.get("speaker", ""),
                "text_kr": (dlg.get("kr", "") or "").strip(),
                "text_en": (dlg.get("en", "") or "").strip(),
                "position": "before" if offset < 0 else "after",
            })

    return adjacent


def _read_lore_chunk(chunk_id: str, include_adjacent: bool) -> dict:
    """lore chunk_id로 원본 YAML 섹션 읽기."""
    # Whoosh 로어 인덱스에서 조회
    ix = _get_lore_searcher()
    with ix.searcher() as searcher:
        results = searcher.search(Term("chunk_id", chunk_id), limit=1)
        if not results:
            return {"chunk_id": chunk_id, "error": f"로어 청크를 찾을 수 없습니다: {chunk_id}"}

        r = results[0]
        entry = {
            "chunk_id": chunk_id,
            "source_type": r["source_type"],
            "source_id": r.get("source_id", ""),
            "section": r.get("section", ""),
            "name_kr": r.get("name_kr", ""),
            "name_en": r.get("name_en", ""),
            "text_kr": r.get("text_kr", ""),
            "text_en": r.get("text_en", ""),
            "source_file": r.get("source_file", ""),
        }

    # 인접 섹션 포함
    if include_adjacent:
        adjacent = _get_adjacent_lore_sections(chunk_id, entry)
        if adjacent:
            entry["adjacent"] = adjacent

    return entry


def _get_adjacent_lore_sections(chunk_id: str, entry: dict) -> list[dict]:
    """같은 엔티티의 인접 섹션을 가져온다."""
    source_file = entry.get("source_file", "")
    if not source_file:
        return []

    lore_path = Path.cwd() / "eb_lore" / source_file
    if not lore_path.exists():
        return []

    try:
        with open(lore_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []

    if not data or not isinstance(data, dict):
        return []

    # chunk_id에서 섹션명 추출: char:fx:basic_info → basic_info
    parts = chunk_id.split(":")
    current_section = parts[-1] if len(parts) >= 3 else ""

    sections = []
    for key, value in data.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        if not ("kr" in value or "en" in value):
            continue
        if key in ("name", "title", "id"):
            continue
        sections.append(key)

    if current_section not in sections:
        return []

    current_idx = sections.index(current_section)
    adjacent = []
    for offset in [-1, 1]:
        adj_idx = current_idx + offset
        if 0 <= adj_idx < len(sections):
            adj_section = sections[adj_idx]
            adj_value = data[adj_section]

            kr = adj_value.get("kr", "")
            en = adj_value.get("en", "")
            if isinstance(kr, list):
                kr = "\n".join(str(v) for v in kr)
            if isinstance(en, list):
                en = "\n".join(str(v) for v in en)

            # chunk_id 재구성
            prefix = ":".join(parts[:-1])
            adj_chunk_id = f"{prefix}:{adj_section}"

            adjacent.append({
                "chunk_id": adj_chunk_id,
                "section": adj_section,
                "text_kr": str(kr).strip() if kr else "",
                "text_en": str(en).strip() if en else "",
                "position": "before" if offset < 0 else "after",
            })

    return adjacent
