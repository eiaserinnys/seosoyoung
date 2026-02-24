"""대사 검색 모듈 테스트."""

import pytest
from pathlib import Path

from whoosh.index import create_in


class TestDialogueSearcher:
    """DialogueSearcher 테스트."""

    @pytest.fixture
    def mock_index(self, tmp_path):
        """테스트용 mock 인덱스 생성."""
        from seosoyoung.search.schema import dialogue_schema

        index_path = tmp_path / "test_index"
        index_path.mkdir()

        ix = create_in(str(index_path), dialogue_schema)

        writer = ix.writer()
        # 테스트 데이터 추가
        writer.add_document(
            dlgId="fx-test-001",
            speaker="fx",
            text_kr="악마를 사냥하는 건 내 전문이야.",
            text_en="Hunting demons is my specialty.",
            hash="abc123",
            source_file="test.yaml",
            labels="r2_act0_a_opening",
            revision="_rev2",
            acts="act0",
            trigger="bk_idle",
        )
        writer.add_document(
            dlgId="ar-test-001",
            speaker="ar",
            text_kr="천사의 축복을 받으세요.",
            text_en="Receive the angel's blessing.",
            hash="def456",
            source_file="test.yaml",
            labels="r2_act0_a_opening",
            revision="_rev2",
            acts="act0",
            trigger="bk_wave",
        )
        writer.add_document(
            dlgId="fx-test-002",
            speaker="fx",
            text_kr="천사라고? 그런 건 존재하지 않아.",
            text_en="An angel? Such things don't exist.",
            hash="ghi789",
            source_file="test2.yaml",
            labels="r2_act1_scene1",
            revision="_rev2",
            acts="act1",
            trigger="",
        )
        writer.add_document(
            dlgId="kl-test-001",
            speaker="kl",
            text_kr="이건 rev1 대사입니다.",
            text_en="This is a rev1 dialogue.",
            hash="jkl012",
            source_file="test_rev1.yaml",
            labels="prologue_a_1",
            revision="_rev1",
            acts="act0",
            trigger="",
        )
        writer.commit()

        return index_path

    @pytest.fixture
    def searcher(self, mock_index):
        """검색기 fixture."""
        from seosoyoung.search import DialogueSearcher

        return DialogueSearcher(mock_index)

    def test_search_korean(self, searcher):
        """한글 검색 테스트."""
        results = searcher.search(query_text="악마", limit=5)
        assert len(results) > 0
        assert "dlgId" in results[0]
        assert "text_kr" in results[0]
        assert "악마" in results[0]["text_kr"]

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
        result = searcher.search_by_dlgid("fx-test-001")

        assert result is not None
        assert result["dlgId"] == "fx-test-001"
        assert result["speaker"] == "fx"

    def test_search_nonexistent_dlgid(self, searcher):
        """존재하지 않는 dlgId 검색."""
        result = searcher.search_by_dlgid("nonexistent-dlgid-12345")
        assert result is None

    def test_get_stats(self, searcher):
        """인덱스 통계 조회."""
        stats = searcher.get_stats()
        assert "total_docs" in stats
        assert stats["total_docs"] == 4  # 4개 문서 추가됨

    def test_search_combined_filters(self, searcher):
        """복합 필터 테스트."""
        results = searcher.search(
            query_text="천사",
            speaker="ar",
            limit=10
        )
        for r in results:
            assert r["speaker"] == "ar"

    def test_search_by_revision(self, searcher):
        """리비전 필터 테스트."""
        results = searcher.search(revision="_rev1", limit=10)
        assert len(results) > 0
        for r in results:
            assert r["revision"] == "_rev1"

    def test_search_by_act(self, searcher):
        """액트 필터 테스트."""
        results = searcher.search(act="act1", limit=10)
        assert len(results) > 0
        for r in results:
            assert "act1" in r["acts"]

    def test_search_by_trigger(self, searcher):
        """트리거 필터 테스트."""
        results = searcher.search(trigger="bk_idle", limit=10)
        assert len(results) > 0
        for r in results:
            assert r["trigger"] == "bk_idle"


class TestGetDefaultIndexPath:
    """get_default_index_path 테스트."""

    def test_get_default_index_path(self):
        """기본 인덱스 경로 반환 테스트."""
        from seosoyoung.search import get_default_index_path

        index_path = get_default_index_path()
        assert ".local" in str(index_path)
        assert "index" in str(index_path)
        assert "dialogues" in str(index_path)


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


class TestDialogueSearcherErrors:
    """DialogueSearcher 에러 처리 테스트."""

    def test_index_not_found(self, tmp_path):
        """인덱스가 없을 때 FileNotFoundError 발생."""
        from seosoyoung.search import DialogueSearcher

        with pytest.raises(FileNotFoundError):
            DialogueSearcher(tmp_path / "nonexistent")
