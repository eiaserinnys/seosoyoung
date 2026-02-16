"""eb_lore 인덱서 테스트."""

import pytest
import yaml
from pathlib import Path

from seosoyoung.search.lore_indexer import LoreIndexer


@pytest.fixture
def lore_tree(tmp_path):
    """테스트용 eb_lore 구조."""
    content = tmp_path / "content"

    # characters
    chars = content / "characters"
    chars.mkdir(parents=True)

    fx_data = {
        "id": "fx",
        "name": {"kr": "펜릭스 헤이븐", "en": "Fenrix Haven"},
        "basic_info": {
            "_title": {"kr": "기본 정보", "en": "Basic Info"},
            "_display": "markdown",
            "kr": "20대 중후반의 악마 사냥꾼.",
            "en": "A demon hunter in his mid-twenties.",
        },
        "background": {
            "_title": {"kr": "배경", "en": "Background"},
            "_display": "markdown",
            "kr": "어릴 적 가족을 잃었다.",
            "en": "Lost his family as a child.",
        },
        "personality": {
            "_title": {"kr": "성격", "en": "Personality"},
            "_display": "list",
            "kr": ["냉소적이다", "실력이 있다"],
            "en": ["Cynical", "Skilled"],
        },
    }
    with open(chars / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(fx_data, f, allow_unicode=True)

    # actor_code.yaml (스킵 대상)
    with open(chars / "actor_code.yaml", "w", encoding="utf-8") as f:
        yaml.dump({"codes": {"fx": "펜릭스"}}, f, allow_unicode=True)

    # glossary
    glossary_data = {
        "id": "glossary",
        "title": {"kr": "용어집", "en": "Glossary"},
        "main_characters": {
            "_title": {"kr": "주요 캐릭터", "en": "Main Characters"},
            "_display": "table",
            "items": [
                {
                    "name": {"kr": "펜릭스 헤이븐", "en": "Fenrix Haven"},
                    "description": {"kr": "주인공", "en": "Protagonist"},
                },
                {
                    "name": {"kr": "아리엘라", "en": "Ariella"},
                    "description": {"kr": "수호자", "en": "Guardian"},
                },
            ],
        },
    }
    with open(content / "glossary.yaml", "w", encoding="utf-8") as f:
        yaml.dump(glossary_data, f, allow_unicode=True)

    # places
    places = content / "places"
    places.mkdir()

    sanctuary_data = {
        "id": "sanctuary",
        "name": {"kr": "망각의 성채", "en": "The Sanctuary of Oblivion"},
        "basic_info": {
            "_title": {"kr": "기본 정보", "en": "Basic Info"},
            "_display": "markdown",
            "kr": "봉인의 중심에 위치한 요새.",
            "en": "A fortress at the center of the seal.",
        },
    }
    with open(places / "sanctuary.yaml", "w", encoding="utf-8") as f:
        yaml.dump(sanctuary_data, f, allow_unicode=True)

    # synopsis
    synopsis = content / "synopsis"
    synopsis.mkdir()

    overview_data = {
        "id": "overview",
        "title": {"kr": "개요", "en": "Overview"},
        "story_summary": {
            "_title": {"kr": "스토리 요약", "en": "Story Summary"},
            "_display": "markdown",
            "kr": "악마사냥꾼 펜릭스의 이야기.",
            "en": "The story of demon hunter Fenrix.",
        },
    }
    with open(synopsis / "overview.yaml", "w", encoding="utf-8") as f:
        yaml.dump(overview_data, f, allow_unicode=True)

    return tmp_path


class TestLoreIndexer:
    """LoreIndexer 테스트."""

    def test_index_all(self, lore_tree, tmp_path):
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        stats = indexer.index_all(force=True)

        assert stats["characters"] > 0
        assert stats["glossary"] > 0
        assert stats["places"] > 0
        assert stats["synopsis"] > 0
        assert len(stats["errors"]) == 0

    def test_character_chunks(self, lore_tree, tmp_path):
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        indexer.index_all(force=True)

        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("chunk_id", "char:fx:basic_info"))
            assert len(results) == 1
            assert "악마 사냥꾼" in results[0]["text_kr"]

    def test_character_list_field(self, lore_tree, tmp_path):
        """리스트 타입 필드도 인덱싱 되는지."""
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        indexer.index_all(force=True)

        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("chunk_id", "char:fx:personality"))
            assert len(results) == 1
            assert "냉소적" in results[0]["text_kr"]

    def test_glossary_chunks(self, lore_tree, tmp_path):
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        indexer.index_all(force=True)

        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("source_type", "glossary"))
            assert len(results) == 2  # 2개 항목

    def test_place_chunks(self, lore_tree, tmp_path):
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        indexer.index_all(force=True)

        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("chunk_id", "place:sanctuary:basic_info"))
            assert len(results) == 1
            assert "요새" in results[0]["text_kr"]

    def test_synopsis_chunks(self, lore_tree, tmp_path):
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        indexer.index_all(force=True)

        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("chunk_id", "synopsis:overview:story_summary"))
            assert len(results) == 1

    def test_skips_actor_code(self, lore_tree, tmp_path):
        """actor_code.yaml은 스킵되어야 한다."""
        index_path = tmp_path / "lore_index"
        indexer = LoreIndexer(lore_tree, index_path)
        stats = indexer.index_all(force=True)

        # actor_code.yaml에는 name 필드가 없으므로 0건 또는 스킵
        from whoosh.index import open_dir
        from whoosh.query import Term

        ix = open_dir(str(index_path))
        with ix.searcher() as s:
            results = s.search(Term("source_id", "actor_code"))
            assert len(results) == 0

    def test_empty_lore(self, tmp_path):
        lore_path = tmp_path / "empty_lore"
        lore_path.mkdir()
        index_path = tmp_path / "lore_index"

        indexer = LoreIndexer(lore_path, index_path)
        stats = indexer.index_all(force=True)

        assert stats["characters"] == 0
        assert stats["glossary"] == 0
        assert stats["places"] == 0
        assert stats["synopsis"] == 0
