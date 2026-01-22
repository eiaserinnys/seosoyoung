"""대사 검색 모듈 테스트."""

import pytest
from pathlib import Path


class TestDialogueSearcher:
    """DialogueSearcher 테스트."""

    @pytest.fixture
    def searcher(self):
        """검색기 fixture - 인덱스가 존재해야 함."""
        from seosoyoung.search import DialogueSearcher, get_default_index_path

        index_path = get_default_index_path()
        if not index_path.exists():
            pytest.skip("Index not found. Run indexer first.")

        return DialogueSearcher(index_path)

    def test_search_korean(self, searcher):
        """한글 검색 테스트."""
        results = searcher.search(query_text="악마", limit=5)
        assert len(results) > 0
        assert "dlgId" in results[0]
        assert "text_kr" in results[0]

    def test_search_with_speaker_filter(self, searcher):
        """화자 필터 테스트."""
        results = searcher.search(speaker="fx", limit=5)
        assert len(results) > 0
        for r in results:
            assert r["speaker"] == "fx"

    def test_search_by_label(self, searcher):
        """레이블 검색 테스트."""
        results = searcher.search(label="r2_act0_a_opening", limit=5)
        assert len(results) > 0
        for r in results:
            assert "r2_act0_a_opening" in r["labels"]

    def test_search_by_dlgid(self, searcher):
        """dlgId로 정확히 검색."""
        # 먼저 아무 대사나 검색해서 dlgId 가져오기
        results = searcher.search(speaker="fx", limit=1)
        if not results:
            pytest.skip("No fx dialogues found")

        dlgId = results[0]["dlgId"]
        result = searcher.search_by_dlgid(dlgId)

        assert result is not None
        assert result["dlgId"] == dlgId

    def test_search_nonexistent_dlgid(self, searcher):
        """존재하지 않는 dlgId 검색."""
        result = searcher.search_by_dlgid("nonexistent-dlgid-12345")
        assert result is None

    def test_get_stats(self, searcher):
        """인덱스 통계 조회."""
        stats = searcher.get_stats()
        assert "total_docs" in stats
        assert stats["total_docs"] > 0

    def test_search_combined_filters(self, searcher):
        """복합 필터 테스트."""
        results = searcher.search(
            query_text="천사",
            speaker="ar",
            limit=10
        )
        for r in results:
            assert r["speaker"] == "ar"


class TestDialogueIndexer:
    """DialogueIndexer 테스트."""

    def test_get_default_paths(self):
        """기본 경로 반환 테스트."""
        from seosoyoung.search import get_default_paths

        narrative_path, index_path = get_default_paths()
        assert "eb_narrative" in str(narrative_path)
        assert "narrative" in str(narrative_path)
        assert "internal" in str(index_path)
        assert "dialogues" in str(index_path)


class TestDialogueReferenceMap:
    """DialogueReferenceMap 테스트."""

    @pytest.fixture
    def ref_map(self):
        """역참조 맵 fixture."""
        from seosoyoung.search.reference import build_reference_map

        narrative_path = Path.cwd() / "eb_narrative" / "narrative"
        if not narrative_path.exists():
            pytest.skip("Narrative path not found")

        return build_reference_map(narrative_path)

    def test_build_reference_map(self, ref_map):
        """역참조 맵 빌드 테스트."""
        stats = ref_map.get_stats()
        assert stats["total_dlgids"] > 0
        assert stats["unique_labels"] > 0

    def test_get_metadata(self, ref_map):
        """메타데이터 조회 테스트."""
        # 아무 dlgId나 가져오기
        if not ref_map._ref_map:
            pytest.skip("Reference map is empty")

        dlgId = next(iter(ref_map._ref_map.keys()))
        meta = ref_map.get(dlgId)

        assert meta is not None
        assert hasattr(meta, "labels")
        assert hasattr(meta, "revisions")
        assert hasattr(meta, "acts")
        assert hasattr(meta, "triggers")


class TestFormatResults:
    """결과 포맷팅 테스트."""

    def test_format_json(self):
        """JSON 포맷 테스트."""
        from seosoyoung.search.searcher import format_results

        results = [
            {"dlgId": "test-001", "speaker": "fx", "text_kr": "테스트", "text_en": "Test"}
        ]
        output = format_results(results, "json")
        assert "test-001" in output
        assert "테스트" in output

    def test_format_brief(self):
        """Brief 포맷 테스트."""
        from seosoyoung.search.searcher import format_results

        results = [
            {"dlgId": "test-001", "speaker": "fx", "text_kr": "테스트 대사입니다.", "text_en": "Test"}
        ]
        output = format_results(results, "brief")
        assert "[FX]" in output
        assert "test-001" in output
