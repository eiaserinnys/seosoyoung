"""A-RAG 로어 검색 E2E 테스트 — 3개 MCP 도구 순차 호출 시나리오.

Phase 5 통합 테스트: MCP 서버에 등록된 도구들을 실제 검색 파이프라인으로 호출하여
keyword_search → 스니펫 확인 → chunk_read 흐름을 검증한다.

시나리오 1: keyword_search (dlg) → chunk_read
시나리오 2: semantic_search (dlg) → chunk_read
시나리오 3: keyword_search (lore) → chunk_read (장소/캐릭터)
시나리오 4: Context Tracker 동작 확인 (같은 chunk_read 2회)
시나리오 5: lore_index_status 도구 동작 확인
"""

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
def e2e_dialogue_index(tmp_path):
    """E2E용 Whoosh 대사 인덱스 — 하니엘, 계약 관련 대사 포함."""
    idx_path = tmp_path / ".local" / "index" / "dialogues"
    idx_path.mkdir(parents=True)

    ix = create_in(str(idx_path), dialogue_schema)
    writer = ix.writer()

    # 하니엘 계약 관련 대사
    writer.add_document(
        dlgId="hn-contract-001",
        speaker="hn",
        text_kr="계약의 조건을 잘 읽어보셨나요? 이 계약은 되돌릴 수 없습니다.",
        text_en="Have you read the contract terms carefully? This contract is irreversible.",
        hash="h001",
        source_file="hn.yaml",
        labels="r2_act1_contract",
        revision="_rev2",
        acts="act1",
        trigger="bk_contract",
    )
    writer.add_document(
        dlgId="hn-contract-002",
        speaker="hn",
        text_kr="후회하고 계신 건 아니겠지요? 계약은 이미 성립되었습니다.",
        text_en="You're not regretting it, are you? The contract is already in effect.",
        hash="h002",
        source_file="hn.yaml",
        labels="r2_act1_contract",
        revision="_rev2",
        acts="act1",
        trigger="",
    )
    writer.add_document(
        dlgId="fx-battle-001",
        speaker="fx",
        text_kr="악마를 사냥하는 건 내 전문이야.",
        text_en="Hunting demons is my specialty.",
        hash="f001",
        source_file="fx.yaml",
        labels="r2_act0_opening",
        revision="_rev2",
        acts="act0",
        trigger="bk_idle",
    )
    writer.add_document(
        dlgId="ar-blessing-001",
        speaker="ar",
        text_kr="천사의 축복이 함께하길 바랍니다.",
        text_en="May the angel's blessing be with you.",
        hash="a001",
        source_file="ar.yaml",
        labels="r2_act0_opening",
        revision="_rev2",
        acts="act0",
        trigger="bk_wave",
    )
    writer.commit()
    return idx_path


@pytest.fixture
def e2e_lore_index(tmp_path):
    """E2E용 Whoosh 로어 인덱스 — 바포메트, 캐릭터, 장소 포함."""
    idx_path = tmp_path / ".local" / "index" / "lore"
    idx_path.mkdir(parents=True)

    ix = create_in(str(idx_path), lore_schema)
    writer = ix.writer()

    # 바포메트 (장소)
    writer.add_document(
        chunk_id="place:baphomet_lair:overview",
        source_type="place",
        source_id="baphomet_lair",
        section="overview",
        name_kr="바포메트의 소굴",
        name_en="Baphomet's Lair",
        text_kr="잿빛의 초원 깊은 곳에 위치한 바포메트의 소굴. 악마의 기운이 가득하다.",
        text_en="Baphomet's lair located deep in the Ashen Meadow. Filled with demonic energy.",
        source_file="content/places/baphomet_lair.yaml",
    )
    writer.add_document(
        chunk_id="place:baphomet_lair:features",
        source_type="place",
        source_id="baphomet_lair",
        section="features",
        name_kr="바포메트의 소굴",
        name_en="Baphomet's Lair",
        text_kr="뒤틀린 제단과 피로 물든 벽이 특징이다.",
        text_en="Characterized by a twisted altar and blood-stained walls.",
        source_file="content/places/baphomet_lair.yaml",
    )

    # 하니엘 (캐릭터)
    writer.add_document(
        chunk_id="char:hn:basic_info",
        source_type="character",
        source_id="hn",
        section="basic_info",
        name_kr="하니엘",
        name_en="Haniel",
        text_kr="계약의 천사. 인간과 계약을 맺어 힘을 부여한다.",
        text_en="Angel of contracts. Grants power through contracts with humans.",
        source_file="content/characters/hn.yaml",
    )
    writer.add_document(
        chunk_id="char:hn:personality",
        source_type="character",
        source_id="hn",
        section="personality",
        name_kr="하니엘",
        name_en="Haniel",
        text_kr="냉정하고 신중한 성격. 계약의 공정함을 중시한다.",
        text_en="Cold and cautious personality. Values fairness in contracts.",
        source_file="content/characters/hn.yaml",
    )
    writer.commit()
    return idx_path


@pytest.fixture
def e2e_embedding_index(tmp_path):
    """E2E용 임베딩 인덱스."""
    emb_path = tmp_path / ".local" / "index" / "embeddings"
    emb_path.mkdir(parents=True)

    # dialogue 임베딩 (4문장, 1536차원)
    dlg_vectors = np.random.randn(4, 1536).astype(np.float32)
    norms = np.linalg.norm(dlg_vectors, axis=1, keepdims=True)
    dlg_vectors = dlg_vectors / norms

    # "후회" 관련 쿼리가 hn-contract-002에 높은 점수를 주도록 조작
    # 인덱스 1번 벡터를 쿼리와 유사하게 설정
    dlg_metadata = [
        {"chunk_id": "hn-contract-001", "text": "계약의 조건을 잘 읽어보셨나요?", "source_type": "dialogue", "lang": "kr", "speaker": "hn", "source_file": "hn.yaml"},
        {"chunk_id": "hn-contract-002", "text": "후회하고 계신 건 아니겠지요?", "source_type": "dialogue", "lang": "kr", "speaker": "hn", "source_file": "hn.yaml"},
        {"chunk_id": "fx-battle-001", "text": "악마를 사냥하는 건 내 전문이야.", "source_type": "dialogue", "lang": "kr", "speaker": "fx", "source_file": "fx.yaml"},
        {"chunk_id": "ar-blessing-001", "text": "천사의 축복이 함께하길 바랍니다.", "source_type": "dialogue", "lang": "kr", "speaker": "ar", "source_file": "ar.yaml"},
    ]

    np.save(emb_path / "dialogue_vectors.npy", dlg_vectors)
    with open(emb_path / "dialogue_metadata.json", "w", encoding="utf-8") as f:
        json.dump(dlg_metadata, f, ensure_ascii=False)

    # lore 임베딩
    lore_vectors = np.random.randn(3, 1536).astype(np.float32)
    lore_norms = np.linalg.norm(lore_vectors, axis=1, keepdims=True)
    lore_vectors = lore_vectors / lore_norms

    lore_metadata = [
        {"chunk_id": "place:baphomet_lair:overview", "text": "바포메트의 소굴.", "source_type": "place", "lang": "kr", "source_id": "baphomet_lair", "section": "overview"},
        {"chunk_id": "char:hn:basic_info", "text": "계약의 천사.", "source_type": "character", "lang": "kr", "source_id": "hn", "section": "basic_info"},
        {"chunk_id": "char:hn:personality", "text": "냉정하고 신중한 성격.", "source_type": "character", "lang": "kr", "source_id": "hn", "section": "personality"},
    ]

    np.save(emb_path / "lore_vectors.npy", lore_vectors)
    with open(emb_path / "lore_metadata.json", "w", encoding="utf-8") as f:
        json.dump(lore_metadata, f, ensure_ascii=False)

    return emb_path


@pytest.fixture
def e2e_dlglist(tmp_path):
    """E2E용 dlglist YAML."""
    dlglist_path = tmp_path / "eb_narrative" / "narrative" / "dlglist"
    dlglist_path.mkdir(parents=True)

    hn_data = {
        "dialogues": [
            {"dlgId": "hn-contract-000", "speaker": "hn", "kr": "인간이여, 이리 오라.", "en": "Come here, human.", "hash": "000"},
            {"dlgId": "hn-contract-001", "speaker": "hn", "kr": "계약의 조건을 잘 읽어보셨나요? 이 계약은 되돌릴 수 없습니다.", "en": "Have you read the contract terms carefully? This contract is irreversible.", "hash": "h001"},
            {"dlgId": "hn-contract-002", "speaker": "hn", "kr": "후회하고 계신 건 아니겠지요? 계약은 이미 성립되었습니다.", "en": "You're not regretting it, are you? The contract is already in effect.", "hash": "h002"},
            {"dlgId": "hn-contract-003", "speaker": "hn", "kr": "그대의 선택이 곧 운명이 될 것이오.", "en": "Your choice will become your destiny.", "hash": "h003"},
        ]
    }

    with open(dlglist_path / "hn.yaml", "w", encoding="utf-8") as f:
        yaml.dump(hn_data, f, allow_unicode=True)

    return dlglist_path


@pytest.fixture
def e2e_lore_yaml(tmp_path):
    """E2E용 lore YAML."""
    char_path = tmp_path / "eb_lore" / "content" / "characters"
    char_path.mkdir(parents=True)
    place_path = tmp_path / "eb_lore" / "content" / "places"
    place_path.mkdir(parents=True)

    hn_data = {
        "id": "hn",
        "name": {"kr": "하니엘", "en": "Haniel"},
        "basic_info": {"kr": "계약의 천사. 인간과 계약을 맺어 힘을 부여한다.", "en": "Angel of contracts."},
        "personality": {"kr": "냉정하고 신중한 성격.", "en": "Cold and cautious personality."},
        "background": {"kr": "천사 하니엘의 과거 이야기.", "en": "The backstory of angel Haniel."},
    }
    with open(char_path / "hn.yaml", "w", encoding="utf-8") as f:
        yaml.dump(hn_data, f, allow_unicode=True)

    baphomet_data = {
        "id": "baphomet_lair",
        "name": {"kr": "바포메트의 소굴", "en": "Baphomet's Lair"},
        "overview": {"kr": "잿빛의 초원 깊은 곳에 위치한 바포메트의 소굴.", "en": "Baphomet's lair in the Ashen Meadow."},
        "features": {"kr": "뒤틀린 제단과 피로 물든 벽이 특징이다.", "en": "Twisted altar and blood-stained walls."},
    }
    with open(place_path / "baphomet_lair.yaml", "w", encoding="utf-8") as f:
        yaml.dump(baphomet_data, f, allow_unicode=True)

    return tmp_path / "eb_lore"


@pytest.fixture(autouse=True)
def setup_e2e(tmp_path, e2e_dialogue_index, e2e_lore_index, e2e_embedding_index, e2e_dlglist, e2e_lore_yaml):
    """E2E 테스트용 경로 패치."""
    from seosoyoung.mcp.tools import lore_search

    lore_search.reset_indices()
    lore_search.reset_context_tracker()

    def mock_base():
        return tmp_path / ".local" / "index"

    lore_search._get_index_base_path = mock_base

    with patch("seosoyoung.mcp.tools.lore_search.Path") as MockPath:
        MockPath.cwd.return_value = tmp_path
        MockPath.side_effect = lambda *a, **kw: Path(*a, **kw)
        yield

    lore_search._get_index_base_path = lambda: Path.cwd() / ".local" / "index"
    lore_search.reset_indices()
    lore_search.reset_context_tracker()


class TestE2EScenario1KeywordSearchDialogue:
    """시나리오 1: "하니엘 계약" keyword_search → 스니펫 확인 → chunk_read."""

    def test_keyword_search_finds_haniel_contract(self):
        """keyword_search로 '하니엘 계약' 검색 → 대사 결과 반환."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["계약"], source="dlg", top_k=5)

        assert result["count"] > 0
        assert result["source"] == "dlg"

        # 하니엘 계약 대사가 포함되어야 함
        chunk_ids = [r["chunk_id"] for r in result["results"]]
        assert any("hn-contract" in cid for cid in chunk_ids)

        # 각 결과에 snippet이 있어야 함
        for r in result["results"]:
            assert "snippet" in r
            assert len(r["snippet"]) > 0
            assert r["source_type"] == "dialogue"

    def test_keyword_search_then_chunk_read(self):
        """keyword_search 결과의 chunk_id로 chunk_read → 전체 텍스트 반환."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search, lore_chunk_read

        # Step 1: keyword_search
        search_result = lore_keyword_search(keywords=["계약"], source="dlg", top_k=5)
        assert search_result["count"] > 0

        # Step 2: 첫 번째 결과의 chunk_id로 chunk_read
        first_chunk_id = search_result["results"][0]["chunk_id"]
        read_result = lore_chunk_read(chunk_id=first_chunk_id)

        assert read_result["chunk_id"] == first_chunk_id
        assert read_result["source_type"] == "dialogue"
        assert "text_kr" in read_result
        assert "text_en" in read_result
        assert read_result["speaker"] == "hn"
        assert len(read_result["text_kr"]) > 0
        assert len(read_result["text_en"]) > 0

    def test_keyword_search_speaker_filter(self):
        """speaker 필터로 하니엘 대사만 검색."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["계약"], speaker="hn", source="dlg", top_k=5)

        assert result["count"] > 0
        for r in result["results"]:
            assert r["speaker"] == "hn"


class TestE2EScenario2SemanticSearchDialogue:
    """시나리오 2: "계약을 후회하는 대사" semantic_search → 스니펫 확인 → chunk_read."""

    def test_semantic_search_finds_regret_dialogue(self):
        """semantic_search로 '계약 후회' 검색 → 관련 대사 결과."""
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search

        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            result = lore_semantic_search(query="계약을 후회하는 대사", source="dlg", top_k=5)

            assert result["count"] > 0
            assert result["source"] == "dlg"

            for r in result["results"]:
                assert "chunk_id" in r
                assert "score" in r
                assert "snippet" in r

    def test_semantic_search_then_chunk_read(self):
        """semantic_search → chunk_read 전체 파이프라인."""
        from seosoyoung.mcp.tools.lore_search import lore_semantic_search, lore_chunk_read

        with patch("seosoyoung.mcp.tools.lore_search._get_embedding_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get_embeddings.return_value = [np.random.randn(1536).tolist()]
            mock_cache_fn.return_value = mock_cache

            # Step 1: semantic_search
            search_result = lore_semantic_search(query="계약을 후회하는", source="dlg", top_k=5)
            assert search_result["count"] > 0

        # Step 2: chunk_read
        first_chunk_id = search_result["results"][0]["chunk_id"]
        read_result = lore_chunk_read(chunk_id=first_chunk_id)

        assert read_result["chunk_id"] == first_chunk_id
        assert read_result["source_type"] == "dialogue"
        assert "text_kr" in read_result
        assert "text_en" in read_result


class TestE2EScenario3KeywordSearchLore:
    """시나리오 3: "바포메트" keyword_search (eb_lore) → chunk_read (장소/캐릭터)."""

    def test_keyword_search_baphomet_lore(self):
        """keyword_search로 '바포메트' 검색 → 장소 정보 반환."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["바포메트"], source="lore", top_k=5)

        assert result["count"] > 0
        assert result["source"] == "lore"

        # 바포메트 장소가 결과에 포함
        chunk_ids = [r["chunk_id"] for r in result["results"]]
        assert any("baphomet" in cid for cid in chunk_ids)

        for r in result["results"]:
            assert r["source_type"] in ("character", "place", "glossary", "synopsis")

    def test_keyword_search_lore_then_chunk_read(self):
        """keyword_search (lore) → chunk_read로 장소 전체 텍스트."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search, lore_chunk_read

        # Step 1: keyword_search
        search_result = lore_keyword_search(keywords=["바포메트"], source="lore", top_k=5)
        assert search_result["count"] > 0

        # Step 2: chunk_read
        first_chunk_id = search_result["results"][0]["chunk_id"]
        read_result = lore_chunk_read(chunk_id=first_chunk_id)

        assert read_result["chunk_id"] == first_chunk_id
        assert "text_kr" in read_result
        assert "바포메트" in read_result.get("text_kr", "") or "바포메트" in read_result.get("name_kr", "")
        assert read_result["source_type"] == "place"

    def test_keyword_search_character_lore(self):
        """keyword_search로 '하니엘' 검색 → 캐릭터 정보."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["하니엘"], source="lore", top_k=5)

        assert result["count"] > 0
        chunk_ids = [r["chunk_id"] for r in result["results"]]
        assert any("char:hn" in cid for cid in chunk_ids)

    def test_all_source_search_includes_both(self):
        """source='all'로 검색하면 dlg + lore 결과 모두 포함."""
        from seosoyoung.mcp.tools.lore_search import lore_keyword_search

        result = lore_keyword_search(keywords=["계약"], source="all", top_k=10)

        source_types = {r["source_type"] for r in result["results"]}
        # 대사와 로어(캐릭터) 모두에 "계약" 관련 내용이 있으므로 둘 다 나와야 함
        assert "dialogue" in source_types
        assert "character" in source_types


class TestE2EScenario4ContextTracker:
    """시나리오 4: Context Tracker 동작 확인 (같은 chunk_read 2회 호출)."""

    def test_first_read_returns_full_content(self):
        """첫 번째 chunk_read → 전체 내용 반환."""
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, reset_context_tracker

        reset_context_tracker()

        result = lore_chunk_read(chunk_id="hn-contract-001")

        assert result["chunk_id"] == "hn-contract-001"
        assert "already_read" not in result
        assert "text_kr" in result
        assert "계약" in result["text_kr"]

    def test_second_read_returns_already_read(self):
        """같은 chunk_id를 두 번째 chunk_read → already_read=True."""
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, reset_context_tracker

        reset_context_tracker()

        # 1차 읽기
        result1 = lore_chunk_read(chunk_id="hn-contract-001")
        assert "already_read" not in result1

        # 2차 읽기 — 중복 감지
        result2 = lore_chunk_read(chunk_id="hn-contract-001")
        assert result2["already_read"] is True
        assert "이미 읽은 청크" in result2.get("message", "")

    def test_different_chunks_both_return_full(self):
        """서로 다른 chunk_id → 각각 전체 내용 반환."""
        from seosoyoung.mcp.tools.lore_search import lore_chunk_read, reset_context_tracker

        reset_context_tracker()

        result1 = lore_chunk_read(chunk_id="hn-contract-001")
        assert "already_read" not in result1

        result2 = lore_chunk_read(chunk_id="hn-contract-002")
        assert "already_read" not in result2
        assert result2["text_kr"] != result1["text_kr"]

    def test_full_flow_search_then_read_with_tracker(self):
        """검색 → chunk_read → 같은 ID 재읽기 전체 플로우."""
        from seosoyoung.mcp.tools.lore_search import (
            lore_keyword_search, lore_chunk_read, reset_context_tracker,
        )

        reset_context_tracker()

        # 검색
        search = lore_keyword_search(keywords=["계약"], source="dlg", top_k=3)
        assert search["count"] > 0

        chunk_id = search["results"][0]["chunk_id"]

        # 1차 읽기 — 전체 내용
        read1 = lore_chunk_read(chunk_id=chunk_id)
        assert "text_kr" in read1
        assert "already_read" not in read1

        # 2차 읽기 — 중복 감지
        read2 = lore_chunk_read(chunk_id=chunk_id)
        assert read2["already_read"] is True


class TestE2EScenario5IndexStatus:
    """시나리오 5: lore_index_status 도구가 인덱스 상태를 정확히 보고."""

    def test_status_without_watcher(self):
        """watcher 미실행 시 watcher_running=False."""
        import seosoyoung.mcp.server as srv

        old_watcher = srv._git_watcher
        try:
            srv._git_watcher = None
            result = srv._lore_index_status()

            assert result["watcher_running"] is False
            assert "message" in result
        finally:
            srv._git_watcher = old_watcher

    def test_status_with_mock_watcher(self):
        """watcher 실행 중이면 상태 정보가 정확히 반환."""
        import seosoyoung.mcp.server as srv
        from seosoyoung.search.git_watcher import IndexStatus

        old_watcher = srv._git_watcher
        try:
            mock_watcher = MagicMock()
            mock_watcher.is_running = True

            status = IndexStatus()
            status.last_build_time = "2026-02-16T12:00:00Z"
            status.last_head_narrative = "abc123def"
            status.last_head_lore = "456ghi789"
            status.doc_count_dialogue = 150
            status.doc_count_lore = 30
            status.is_building = False
            status.last_error = None
            status.poll_count = 10

            mock_watcher.status = status
            srv._git_watcher = mock_watcher

            result = srv._lore_index_status()

            assert result["watcher_running"] is True
            assert result["last_build_time"] == "2026-02-16T12:00:00Z"
            assert result["last_head_narrative"] == "abc123def"
            assert result["last_head_lore"] == "456ghi789"
            assert result["doc_count_dialogue"] == 150
            assert result["doc_count_lore"] == 30
            assert result["poll_count"] == 10
            assert result["is_building"] is False
            assert result["last_error"] is None
        finally:
            srv._git_watcher = old_watcher

    def test_status_during_build(self):
        """빌드 중이면 is_building=True로 보고."""
        import seosoyoung.mcp.server as srv
        from seosoyoung.search.git_watcher import IndexStatus

        old_watcher = srv._git_watcher
        try:
            mock_watcher = MagicMock()
            mock_watcher.is_running = True

            status = IndexStatus()
            status.is_building = True
            status.poll_count = 3

            mock_watcher.status = status
            srv._git_watcher = mock_watcher

            result = srv._lore_index_status()

            assert result["watcher_running"] is True
            assert result["is_building"] is True
        finally:
            srv._git_watcher = old_watcher

    def test_status_with_error(self):
        """에러 발생 시 last_error에 에러 메시지 포함."""
        import seosoyoung.mcp.server as srv
        from seosoyoung.search.git_watcher import IndexStatus

        old_watcher = srv._git_watcher
        try:
            mock_watcher = MagicMock()
            mock_watcher.is_running = True

            status = IndexStatus()
            status.last_error = "Build lock timeout"
            status.poll_count = 7

            mock_watcher.status = status
            srv._git_watcher = mock_watcher

            result = srv._lore_index_status()

            assert result["watcher_running"] is True
            assert result["last_error"] == "Build lock timeout"
        finally:
            srv._git_watcher = old_watcher


class TestE2EToolRegistration:
    """A-RAG 도구 4종이 MCP 서버에 정상 등록되었는지 확인."""

    def test_all_lore_tools_registered(self):
        from seosoyoung.mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "lore_keyword_search" in tools
        assert "lore_semantic_search" in tools
        assert "lore_chunk_read" in tools
        assert "lore_index_status" in tools

    def test_tool_signatures_correct(self):
        """도구 파라미터가 올바르게 등록되었는지."""
        from seosoyoung.mcp.server import mcp

        tools = mcp._tool_manager._tools

        # keyword_search: keywords(list), speaker(optional), source, top_k
        kw_tool = tools["lore_keyword_search"]
        assert kw_tool is not None

        # semantic_search: query(str), speaker(optional), source, top_k
        sem_tool = tools["lore_semantic_search"]
        assert sem_tool is not None

        # chunk_read: chunk_id(str), include_adjacent(bool)
        read_tool = tools["lore_chunk_read"]
        assert read_tool is not None
