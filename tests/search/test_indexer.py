"""DialogueIndexer + DialogueReferenceMap 테스트."""

import pytest
import yaml
from pathlib import Path

from seosoyoung.slackbot.search.indexer import (
    DialogueIndexer,
    DialogueReferenceMap,
    DialogueMetadata,
)


class TestDialogueReferenceMap:
    """DialogueReferenceMap 테스트."""

    @pytest.fixture
    def narrative_tree(self, tmp_path):
        """테스트용 narrative 구조 생성."""
        rev1 = tmp_path / "_rev1" / "_core" / "act0"
        rev1.mkdir(parents=True)

        structure = {
            "act": ["act0"],
            "dialogues": [
                {
                    "label": "opening_scene",
                    "trigger": "bk_idle",
                    "dialogue": [
                        {"dlgId": "fx-001"},
                        {"dlgId": "ar-001"},
                    ],
                    "pre_bk": ["fx-002"],
                    "bk_var": [
                        {"bk": ["fx-003", "ar-002"]}
                    ],
                }
            ],
        }

        with open(rev1 / "scene1.yaml", "w", encoding="utf-8") as f:
            yaml.dump(structure, f, allow_unicode=True)

        return tmp_path

    def test_build_creates_ref_map(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        result = ref_map.build()

        assert "fx-001" in result
        assert "ar-001" in result
        assert "fx-002" in result
        assert "fx-003" in result
        assert "ar-002" in result

    def test_metadata_labels(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        meta = ref_map.get("fx-001")
        assert meta is not None
        assert "opening_scene" in meta.labels

    def test_metadata_revision(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        meta = ref_map.get("fx-001")
        assert "_rev1" in meta.revisions

    def test_metadata_acts(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        meta = ref_map.get("fx-001")
        assert "act0" in meta.acts

    def test_metadata_trigger(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        meta = ref_map.get("fx-001")
        assert "bk_idle" in meta.triggers

    def test_get_nonexistent(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        assert ref_map.get("nonexistent") is None

    def test_get_stats(self, narrative_tree):
        ref_map = DialogueReferenceMap(narrative_tree)
        ref_map.build()

        stats = ref_map.get_stats()
        assert stats["total_dlgids"] == 5
        assert stats["unique_labels"] == 1
        assert stats["unique_triggers"] == 1

    def test_empty_narrative(self, tmp_path):
        ref_map = DialogueReferenceMap(tmp_path)
        ref_map.build()

        stats = ref_map.get_stats()
        assert stats["total_dlgids"] == 0


class TestDialogueIndexer:
    """DialogueIndexer 테스트."""

    @pytest.fixture
    def narrative_with_dlglist(self, tmp_path):
        """dlglist + 구조 파일을 갖춘 narrative 디렉토리."""
        # dlglist 파일
        dlglist = tmp_path / "dlglist"
        dlglist.mkdir()

        dlglist_data = {
            "dialogues": [
                {
                    "dlgId": "fx-test-001",
                    "speaker": "fx",
                    "kr": "악마를 사냥하러 가자.",
                    "en": "Let's go hunt demons.",
                    "hash": "abc123",
                },
                {
                    "dlgId": "ar-test-001",
                    "speaker": "ar",
                    "kr": "성채를 지켜야 해.",
                    "en": "We must protect the sanctuary.",
                    "hash": "def456",
                },
            ]
        }

        with open(dlglist / "test.yaml", "w", encoding="utf-8") as f:
            yaml.dump(dlglist_data, f, allow_unicode=True)

        # 구조 파일
        rev1 = tmp_path / "_rev1" / "_core" / "act0"
        rev1.mkdir(parents=True)

        structure = {
            "dialogues": [
                {
                    "label": "test_label",
                    "trigger": "bk_idle",
                    "dialogue": [{"dlgId": "fx-test-001"}],
                }
            ]
        }

        with open(rev1 / "scene.yaml", "w", encoding="utf-8") as f:
            yaml.dump(structure, f, allow_unicode=True)

        return tmp_path

    def test_index_all(self, narrative_with_dlglist, tmp_path):
        index_path = tmp_path / "index"
        indexer = DialogueIndexer(narrative_with_dlglist, index_path)

        stats = indexer.index_all(force=True)

        assert stats["files"] == 1
        assert stats["dialogues"] == 2
        assert stats["with_metadata"] == 1
        assert len(stats["errors"]) == 0

    def test_index_creates_searchable_index(self, narrative_with_dlglist, tmp_path):
        index_path = tmp_path / "index"
        indexer = DialogueIndexer(narrative_with_dlglist, index_path)
        indexer.index_all(force=True)

        from seosoyoung.slackbot.search.searcher import DialogueSearcher

        searcher = DialogueSearcher(index_path)
        result = searcher.search_by_dlgid("fx-test-001")

        assert result is not None
        assert result["speaker"] == "fx"
        assert "악마" in result["text_kr"]

    def test_index_missing_dlglist(self, tmp_path):
        narrative_path = tmp_path / "empty_narrative"
        narrative_path.mkdir()
        index_path = tmp_path / "index"

        indexer = DialogueIndexer(narrative_path, index_path)
        stats = indexer.index_all(force=True)

        assert stats["files"] == 0
        assert len(stats["errors"]) == 1

    def test_index_force_rebuild(self, narrative_with_dlglist, tmp_path):
        index_path = tmp_path / "index"
        indexer = DialogueIndexer(narrative_with_dlglist, index_path)

        stats1 = indexer.index_all(force=True)
        stats2 = indexer.index_all(force=True)

        assert stats1["dialogues"] == stats2["dialogues"]
