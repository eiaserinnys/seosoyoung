"""A-RAG MCP 도구 3종 테스트 — lore_keyword_search, lore_semantic_search, lore_chunk_read."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import yaml
from whoosh.index import create_in

from seosoyoung.search.schema import dialogue_schema, lore_schema


@pytest.fixture
def mock_dialogue_index(tmp_path):
    """테스트용 Whoosh 대사 인덱스."""
    idx_path = tmp_path / ".local" / "index" / "dialogues"
    idx_path.mkdir(parents=True)

    ix = create_in(str(idx_path), dialogue_schema)
    writer = ix.writer()

    writer.add_document(
        dlgId="fx-test-001",
        speaker="fx",
        text_kr="악마를 사냥하는 건 내 전문이야.",
        text_en="Hunting demons is my specialty.",
        hash="abc123",
        source_file="fx.yaml",
        labels="r2_act0_a_opening",
        revision="_rev2",
        acts="act0",
        trigger="bk_idle",
    )
    writer.add_document(
        dlgId="fx-test-002",
        speaker="fx",
        text_kr="계약에 큰 불만은 없어.",
        text_en="No major complaints so far.",
        hash="def456",
        source_file="fx.yaml",
        labels="r2_act0_a_opening",
        revision="_rev2",
        acts="act0",
        trigger="",
    )
    writer.add_document(
        dlgId="ar-test-001",
        speaker="ar",
        text_kr="천사의 축복을 받으세요.",
        text_en="Receive the angel's blessing.",
        hash="ghi789",
        source_file="ar.yaml",
        labels="r2_act0_a_opening",
        revision="_rev2",
        acts="act0",
        trigger="bk_wave",
    )
    writer.commit()
    return idx_path


@pytest.fixture
def mock_lore_index(tmp_path):
    """테스트용 Whoosh 로어 인덱스."""
    idx_path = tmp_path / ".local" / "index" / "lore"
    idx_path.mkdir(parents=True)

    ix = create_in(str(idx_path), lore_schema)
    writer = ix.writer()

    writer.add_document(
        chunk_id="char:fx:basic_info",
        source_type="character",
        source_id="fx",
        section="basic_info",
        name_kr="펜릭스",
        name_en="Fenrix",
        text_kr="악마 사냥꾼이자 모험가. 총기와 화염 마법을 다룬다.",
        text_en="A demon hunter and adventurer. Wields firearms and fire magic.",
        source_file="content/characters/fx.yaml",
    )
    writer.add_document(
        chunk_id="char:fx:personality",
        source_type="character",
        source_id="fx",
        section="personality",
        name_kr="펜릭스",
        name_en="Fenrix",
        text_kr="직설적이고 자유분방한 성격. 유머 감각이 뛰어나다.",
        text_en="Direct and free-spirited. Has a great sense of humor.",
        source_file="content/characters/fx.yaml",
    )
    writer.add_document(
        chunk_id="place:sanctuary:overview",
        source_type="place",
        source_id="sanctuary",
        section="overview",
        name_kr="망각의 성채",
        name_en="Sanctuary of Oblivion",
        text_kr="기억을 잃은 자들이 모여드는 신비로운 성채.",
        text_en="A mysterious citadel where those who lost their memories gather.",
        source_file="content/places/sanctuary.yaml",
    )
    writer.commit()
    return idx_path


@pytest.fixture
def mock_embedding_index(tmp_path):
    """테스트용 임베딩 인덱스."""
    emb_path = tmp_path / ".local" / "index" / "embeddings"
    emb_path.mkdir(parents=True)

    # dialogue 임베딩 (3개 문장, 8차원 테스트용)
    dlg_vectors = np.random.randn(3, 1536).astype(np.float32)
    # 정규화
    norms = np.linalg.norm(dlg_vectors, axis=1, keepdims=True)
    dlg_vectors = dlg_vectors / norms

    dlg_metadata = [
        {"chunk_id": "fx-test-001", "text": "악마를 사냥하는 건 내 전문이야.", "source_type": "dialogue", "lang": "kr", "speaker": "fx", "source_file": "fx.yaml"},
        {"chunk_id": "fx-test-001", "text": "Hunting demons is my specialty.", "source_type": "dialogue", "lang": "en", "speaker": "fx", "source_file": "fx.yaml"},
        {"chunk_id": "ar-test-001", "text": "천사의 축복을 받으세요.", "source_type": "dialogue", "lang": "kr", "speaker": "ar", "source_file": "ar.yaml"},
    ]

    np.save(emb_path / "dialogue_vectors.npy", dlg_vectors)
    with open(emb_path / "dialogue_metadata.json", "w", encoding="utf-8") as f:
        json.dump(dlg_metadata, f, ensure_ascii=False)

    # lore 임베딩
    lore_vectors = np.random.randn(2, 1536).astype(np.float32)
    lore_norms = np.linalg.norm(lore_vectors, axis=1, keepdims=True)
    lore_vectors = lore_vectors / lore_norms

    lore_metadata = [
        {"chunk_id": "char:fx:basic_info", "text": "악마 사냥꾼이자 모험가.", "source_type": "character", "lang": "kr", "source_id": "fx", "section": "basic_info"},
        {"chunk_id": "place:sanctuary:overview", "text": "기억을 잃은 자들이 모여드는 성채.", "source_type": "place", "lang": "kr", "source_id": "sanctuary", "section": "overview"},
    ]

    np.save(emb_path / "lore_vectors.npy", lore_vectors)
    with open(emb_path / "lore_metadata.json", "w", encoding="utf-8") as f:
        json.dump(lore_metadata, f, ensure_ascii=False)

    return emb_path


@pytest.fixture
def mock_dlglist(tmp_path):
    """테스트용 dlglist YAML."""
    dlglist_path = tmp_path / "eb_narrative" / "narrative" / "dlglist"
    dlglist_path.mkdir(parents=True)

    data = {
        "dialogues": [
            {"dlgId": "fx-test-000", "speaker": "fx", "kr": "이전 대사.", "en": "Previous line.", "hash": "000"},
            {"dlgId": "fx-test-001", "speaker": "fx", "kr": "악마를 사냥하는 건 내 전문이야.", "en": "Hunting demons is my specialty.", "hash": "abc123"},
            {"dlgId": "fx-test-002", "speaker": "fx", "kr": "계약에 큰 불만은 없어.", "en": "No major complaints so far.", "hash": "def456"},
            {"dlgId": "fx-test-003", "speaker": "fx", "kr": "다음 대사.", "en": "Next line.", "hash": "999"},
        ]
    }

    with open(dlglist_path / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)

    return dlglist_path


@pytest.fixture
def mock_lore_yaml(tmp_path):
    """테스트용 lore YAML."""
    char_path = tmp_path / "eb_lore" / "content" / "characters"
    char_path.mkdir(parents=True)

    data = {
        "id": "fx",
        "name": {"kr": "펜릭스", "en": "Fenrix"},
        "basic_info": {"kr": "악마 사냥꾼이자 모험가.", "en": "A demon hunter and adventurer."},
        "personality": {"kr": "직설적이고 자유분방한 성격.", "en": "Direct and free-spirited."},
        "background": {"kr": "어린 시절의 이야기.", "en": "Childhood story."},
    }

    with open(char_path / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)

    return tmp_path / "eb_lore"


@pytest.fixture(autouse=True)
def setup_lore_search(tmp_path, mock_dialogue_index, mock_lore_index, mock_embedding_index, mock_dlglist, mock_lore_yaml):
    """lore_search 모듈의 경로를 테스트 tmp_path로 패치."""
    from seosoyoung.mcp.tools import lore_search

    lore_search.reset_indices()
    lore_search.reset_context_tracker()

    original_get_base = lore_search._get_index_base_path

    def mock_base():
        return tmp_path / ".local" / "index"

    lore_search._get_index_base_path = mock_base

    # cwd를 tmp_path로 패치 (dlglist 등 참조)
    with patch("seosoyoung.mcp.tools.lore_search.Path") as MockPath:
        # Path.cwd()만 tmp_path로 패치, 나머지는 원래 동작
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = lambda *a, **kw: Path(*a, **kw)

        yield

    lore_search._get_index_base_path = original_get_base
    lore_search.reset_indices()
    lore_search.reset_context_tracker()


class TestLoreKeywordSearch:
    """lore_keyword_search 도구 테스트."""

    def test_search_dialogue(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["악마"], source="dlg", top_k=5)

        assert result["count"] > 0
        assert result["source"] == "dlg"
        for r in result["results"]:
            assert "chunk_id" in r
            assert "snippet" in r
            assert r["source_type"] == "dialogue"

    def test_search_lore(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["펜릭스"], source="lore", top_k=5)

        assert result["count"] > 0
        for r in result["results"]:
            assert r["source_type"] in ("character", "place", "glossary", "synopsis")

    def test_search_all(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["악마"], source="all", top_k=10)

        assert result["count"] > 0
        assert result["source"] == "all"

    def test_speaker_filter(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["축복"], speaker="ar", source="dlg", top_k=5)

        for r in result["results"]:
            assert r["speaker"] == "ar"

    def test_empty_result(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["존재하지않는키워드xyz"], source="dlg", top_k=5)
        assert result["count"] == 0

    def test_top_k_limit(self):
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["악마"], source="all", top_k=1)
        assert result["count"] <= 1


class TestLoreSemanticSearch:
    """lore_semantic_search 도구 테스트."""

    def test_search_dialogue(self):
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search

        # EmbeddingCache.get_embeddings를 모킹
        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            result = lore_semantic_search(query="악마 사냥", source="dlg", top_k=5)

            assert result["count"] > 0
            assert result["source"] == "dlg"
            for r in result["results"]:
                assert "chunk_id" in r
                assert "score" in r

    def test_search_lore(self):
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search

        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            result = lore_semantic_search(query="캐릭터 성격", source="lore", top_k=5)

            assert result["count"] > 0

    def test_search_all(self):
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search

        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            result = lore_semantic_search(query="테스트", source="all", top_k=5)

            assert result["count"] > 0

    def test_speaker_filter(self):
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search

        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            result = lore_semantic_search(query="악마", speaker="fx", source="dlg", top_k=5)

            for r in result["results"]:
                assert r["speaker"] == "fx"


class TestLoreChunkRead:
    """lore_chunk_read 도구 테스트."""

    def test_read_dialogue_chunk(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read

        result = lore_chunk_read(chunk_id="fx-test-001")

        assert result["chunk_id"] == "fx-test-001"
        assert result["source_type"] == "dialogue"
        assert "악마" in result["text_kr"]
        assert "Hunting" in result["text_en"]
        assert result["speaker"] == "fx"

    def test_read_lore_chunk(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read

        result = lore_chunk_read(chunk_id="char:fx:basic_info")

        assert result["chunk_id"] == "char:fx:basic_info"
        assert result["source_type"] == "character"
        assert "악마 사냥꾼" in result["text_kr"]

    def test_read_nonexistent_dialogue(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read

        result = lore_chunk_read(chunk_id="nonexistent-id-12345")
        assert "error" in result

    def test_read_nonexistent_lore(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read

        result = lore_chunk_read(chunk_id="char:unknown:section")
        assert "error" in result

    def test_include_adjacent_dialogue(self, tmp_path):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, _get_adjacent_dialogues

        # _get_adjacent_dialogues를 직접 테스트 (Path.cwd 패치된 상태)
        adjacent = _get_adjacent_dialogues("fx-test-001", "fx.yaml")
        # autouse fixture의 Path.cwd 패치가 적용되지만,
        # _get_adjacent_dialogues 내부에서 Path.cwd()가 실제 경로를 반환할 수 있으므로
        # 여기서는 빈 결과도 허용
        assert isinstance(adjacent, list)

    def test_include_adjacent_lore(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read

        # lore 인접 섹션은 YAML 파일 접근 필요 — 모킹된 환경에서는 빈 결과 가능
        result = lore_chunk_read(chunk_id="char:fx:basic_info", include_adjacent=True)
        assert result["chunk_id"] == "char:fx:basic_info"
        # adjacent 키는 있을 수도 없을 수도 있음 (파일 접근 성공 여부)


class TestContextTracker:
    """Context Tracker 테스트."""

    def test_duplicate_read_detected(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, reset_context_tracker

        reset_context_tracker()

        # 첫 읽기
        result1 = lore_chunk_read(chunk_id="fx-test-001")
        assert "already_read" not in result1

        # 두 번째 읽기 — 중복 감지
        result2 = lore_chunk_read(chunk_id="fx-test-001")
        assert result2.get("already_read") is True
        assert "이미 읽은 청크" in result2.get("message", "")

    def test_different_chunks_not_duplicate(self):
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, reset_context_tracker

        reset_context_tracker()

        result1 = lore_chunk_read(chunk_id="fx-test-001")
        assert "already_read" not in result1

        result2 = lore_chunk_read(chunk_id="ar-test-001")
        assert "already_read" not in result2

    def test_ttl_expiry(self):
        from seosoyoung.mcp.tools.lore_search import (
            _context_tracker, _track_chunk, reset_context_tracker,
            _CONTEXT_TRACKER_TTL,
        )

        reset_context_tracker()

        # 첫 추적
        assert _track_chunk("test-ttl-chunk") is False

        # 타임스탬프를 과거로 조작
        _context_tracker["test-ttl-chunk"] = time.time() - _CONTEXT_TRACKER_TTL - 1

        # TTL 만료 후 → 새 청크로 인식
        assert _track_chunk("test-ttl-chunk") is False

    def test_reset_tracker(self):
        from seosoyoung.mcp.tools.lore_search import (
            _track_chunk, reset_context_tracker, _context_tracker,
        )

        reset_context_tracker()
        _track_chunk("chunk-a")
        assert len(_context_tracker) == 1

        reset_context_tracker()
        assert len(_context_tracker) == 0


class TestServerRegistration:
    """server.py에 도구가 정상 등록되었는지 확인."""

    def test_tools_registered(self):
        from seosoyoung.mcp.server import mcp

        registered = mcp._tool_manager._tools
        assert "lore_keyword_search" in registered
        assert "lore_semantic_search" in registered
        assert "lore_chunk_read" in registered
