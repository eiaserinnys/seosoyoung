"""통합 빌드 스크립트 테스트."""

import json
import pytest
import yaml
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

from seosoyoung.search.build import build_all, build_whoosh, build_embeddings


def _mock_get_embeddings(texts):
    """텍스트마다 결정적 가짜 벡터 반환."""
    results = []
    for t in texts:
        rng = np.random.RandomState(hash(t) % (2**31))
        vec = rng.randn(1536).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        results.append(vec.tolist())
    return results


@pytest.fixture
def full_data_tree(tmp_path):
    """dlglist + eb_lore 모두 있는 테스트 구조."""
    # DialogueIndexer는 narrative_path/dlglist, DialogueReferenceMap은 narrative_path/_rev1
    # EmbeddingIndexBuilder는 narrative_path/narrative/dlglist
    narrative_root = tmp_path / "narrative_root"

    # Whoosh용: narrative_root/dlglist
    dlglist = narrative_root / "dlglist"
    dlglist.mkdir(parents=True)

    # Embedding용: narrative_root/narrative/dlglist
    emb_dlglist = narrative_root / "narrative" / "dlglist"
    emb_dlglist.mkdir(parents=True)

    # rev1 구조도 생성 (DialogueReferenceMap 용)
    rev1 = narrative_root / "_rev1" / "_core"
    rev1.mkdir(parents=True)

    dlg_data = {
        "speaker": "fx",
        "dialogues": [
            {
                "dlgId": "fx-001",
                "speaker": "fx",
                "kr": "테스트 대사입니다.",
                "en": "This is a test dialogue.",
            }
        ],
    }
    # 양쪽에 동일 데이터
    with open(dlglist / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(dlg_data, f, allow_unicode=True)
    with open(emb_dlglist / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(dlg_data, f, allow_unicode=True)

    # eb_lore
    lore = tmp_path / "lore_root" / "content"
    chars = lore / "characters"
    chars.mkdir(parents=True)

    char_data = {
        "id": "fx",
        "name": {"kr": "펜릭스", "en": "Fenrix"},
        "basic_info": {
            "kr": "악마 사냥꾼.",
            "en": "A demon hunter.",
        },
    }
    with open(chars / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(char_data, f, allow_unicode=True)

    # glossary
    with open(lore / "glossary.yaml", "w", encoding="utf-8") as f:
        yaml.dump({}, f)

    return {
        "narrative_path": tmp_path / "narrative_root",
        "lore_path": tmp_path / "lore_root",
        "index_root": tmp_path / "index",
    }


class TestBuildWhoosh:
    def test_builds_whoosh_indices(self, full_data_tree):
        paths = full_data_tree
        stats = build_whoosh(
            narrative_path=paths["narrative_path"],
            lore_path=paths["lore_path"],
            index_root=paths["index_root"],
            force=True,
        )
        assert stats["dialogue"]["dialogues"] >= 1
        assert "lore" in stats


class TestBuildEmbeddings:
    def test_builds_embedding_indices(self, full_data_tree):
        paths = full_data_tree
        emb_dir = paths["index_root"] / "embeddings"

        with patch(
            "seosoyoung.search.build.EmbeddingIndexBuilder"
        ) as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_dialogue_index.return_value = {
                "total_sentences": 5,
                "total_dialogues": 1,
            }
            mock_instance.build_lore_index.return_value = {
                "total_sentences": 3,
                "total_chunks": 1,
            }
            MockBuilder.return_value = mock_instance

            stats = build_embeddings(
                narrative_path=paths["narrative_path"],
                lore_path=paths["lore_path"],
                index_root=paths["index_root"],
            )

        assert stats["dialogue"]["total_sentences"] == 5
        assert stats["lore"]["total_sentences"] == 3


class TestBuildAll:
    def test_builds_both(self, full_data_tree):
        paths = full_data_tree

        with patch(
            "seosoyoung.search.build.EmbeddingIndexBuilder"
        ) as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_dialogue_index.return_value = {
                "total_sentences": 5,
                "total_dialogues": 1,
            }
            mock_instance.build_lore_index.return_value = {
                "total_sentences": 3,
                "total_chunks": 1,
            }
            MockBuilder.return_value = mock_instance

            stats = build_all(
                narrative_path=paths["narrative_path"],
                lore_path=paths["lore_path"],
                index_root=paths["index_root"],
                force=True,
            )

        assert "whoosh" in stats
        assert "embedding" in stats

    def test_whoosh_only(self, full_data_tree):
        paths = full_data_tree

        stats = build_all(
            narrative_path=paths["narrative_path"],
            lore_path=paths["lore_path"],
            index_root=paths["index_root"],
            whoosh_only=True,
            force=True,
        )

        assert "whoosh" in stats
        assert "embedding" not in stats

    def test_embedding_only(self, full_data_tree):
        paths = full_data_tree

        with patch(
            "seosoyoung.search.build.EmbeddingIndexBuilder"
        ) as MockBuilder:
            mock_instance = MagicMock()
            mock_instance.build_dialogue_index.return_value = {
                "total_sentences": 5,
                "total_dialogues": 1,
            }
            mock_instance.build_lore_index.return_value = {
                "total_sentences": 3,
                "total_chunks": 1,
            }
            MockBuilder.return_value = mock_instance

            stats = build_all(
                narrative_path=paths["narrative_path"],
                lore_path=paths["lore_path"],
                index_root=paths["index_root"],
                embedding_only=True,
            )

        assert "embedding" in stats
        assert "whoosh" not in stats
