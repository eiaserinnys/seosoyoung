"""임베딩 인덱스 빌더 + 코사인 유사도 검색 테스트."""

import json
import numpy as np
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from seosoyoung.search.embedding_index import (
    EmbeddingIndexBuilder,
    cosine_similarity_search,
    load_embedding_index,
)


# -- fixtures --


@pytest.fixture
def dlglist_tree(tmp_path):
    """테스트용 dlglist 구조."""
    narrative = tmp_path / "narrative"
    dlglist = narrative / "dlglist"
    dlglist.mkdir(parents=True)

    fx_data = {
        "speaker": "fx",
        "dialogues": [
            {
                "dlgId": "fx-001TEST",
                "speaker": "fx",
                "kr": "악마를 사냥해야 한다. 그것이 나의 운명이다.",
                "en": "I must hunt the demons. That is my fate.",
            },
            {
                "dlgId": "fx-002TEST",
                "speaker": "fx",
                "kr": "천사의 축복이 필요하다.",
                "en": "I need the angel's blessing.",
            },
        ],
    }
    with open(dlglist / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(fx_data, f, allow_unicode=True)

    ar_data = {
        "speaker": "ar",
        "dialogues": [
            {
                "dlgId": "ar-001TEST",
                "speaker": "ar",
                "kr": "이 검은 오래된 유물이다.",
                "en": "This sword is an ancient relic.",
            },
        ],
    }
    with open(dlglist / "ar.yaml", "w", encoding="utf-8") as f:
        yaml.dump(ar_data, f, allow_unicode=True)

    return tmp_path


@pytest.fixture
def lore_tree(tmp_path):
    """테스트용 eb_lore 구조."""
    content = tmp_path / "content"

    # characters
    chars = content / "characters"
    chars.mkdir(parents=True)

    fx_char = {
        "id": "fx",
        "name": {"kr": "펜릭스 헤이븐", "en": "Fenrix Haven"},
        "basic_info": {
            "_title": {"kr": "기본 정보"},
            "kr": "20대 중후반의 악마 사냥꾼. 냉소적 성격.",
            "en": "A demon hunter in his mid-twenties. Cynical personality.",
        },
    }
    with open(chars / "fx.yaml", "w", encoding="utf-8") as f:
        yaml.dump(fx_char, f, allow_unicode=True)

    # glossary
    glossary = {
        "main_chars": {
            "items": [
                {
                    "name": {"kr": "펜릭스", "en": "Fenrix"},
                    "description": {"kr": "주인공", "en": "Protagonist"},
                }
            ]
        }
    }
    with open(content / "glossary.yaml", "w", encoding="utf-8") as f:
        yaml.dump(glossary, f, allow_unicode=True)

    # places
    places = content / "places"
    places.mkdir()
    sanctuary = {
        "id": "sanctuary",
        "name": {"kr": "망각의 성채", "en": "The Sanctuary"},
        "basic_info": {
            "kr": "봉인의 중심에 위치한 요새.",
            "en": "A fortress at the center of the seal.",
        },
    }
    with open(places / "sanctuary.yaml", "w", encoding="utf-8") as f:
        yaml.dump(sanctuary, f, allow_unicode=True)

    # synopsis
    synopsis = content / "synopsis"
    synopsis.mkdir()
    overview = {
        "id": "overview",
        "title": {"kr": "개요", "en": "Overview"},
        "story_summary": {
            "kr": "악마사냥꾼 펜릭스의 이야기.",
            "en": "The story of demon hunter Fenrix.",
        },
    }
    with open(synopsis / "overview.yaml", "w", encoding="utf-8") as f:
        yaml.dump(overview, f, allow_unicode=True)

    return tmp_path


def _make_fake_embedding(dim=1536):
    """재현 가능한 가짜 임베딩 생성."""
    rng = np.random.RandomState(42)
    vec = rng.randn(dim).astype(np.float32)
    return (vec / np.linalg.norm(vec)).tolist()


def _mock_get_embeddings(texts):
    """텍스트마다 결정적 가짜 벡터 반환."""
    results = []
    for i, t in enumerate(texts):
        rng = np.random.RandomState(hash(t) % (2**31))
        vec = rng.randn(1536).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        results.append(vec.tolist())
    return results


# -- EmbeddingIndexBuilder 테스트 --


class TestEmbeddingIndexBuilder:
    def test_build_dialogue_embeddings(self, dlglist_tree, tmp_path):
        """dlglist 대사를 문장 분할 → 임베딩으로 변환."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=dlglist_tree,
            lore_path=None,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            stats = builder.build_dialogue_index()

        assert stats["total_sentences"] > 0
        assert stats["total_dialogues"] == 3  # fx 2개 + ar 1개
        assert (output_dir / "dialogue_vectors.npy").exists()
        assert (output_dir / "dialogue_metadata.json").exists()

    def test_build_lore_embeddings(self, lore_tree, tmp_path):
        """eb_lore 텍스트를 문장 분할 → 임베딩으로 변환."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=None,
            lore_path=lore_tree,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            stats = builder.build_lore_index()

        assert stats["total_sentences"] > 0
        assert stats["total_chunks"] > 0
        assert (output_dir / "lore_vectors.npy").exists()
        assert (output_dir / "lore_metadata.json").exists()

    def test_metadata_has_parent_chunk_ref(self, dlglist_tree, tmp_path):
        """각 문장 메타데이터가 부모 청크(dlgId)를 참조하는지."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=dlglist_tree,
            lore_path=None,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            builder.build_dialogue_index()

        with open(output_dir / "dialogue_metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # 모든 메타데이터에 chunk_id(=dlgId) 존재
        for entry in metadata:
            assert "chunk_id" in entry
            assert "text" in entry
            assert "source_type" in entry
            assert entry["source_type"] == "dialogue"

    def test_lore_metadata_has_parent_chunk_ref(self, lore_tree, tmp_path):
        """로어 문장 메타데이터가 부모 청크를 참조하는지."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=None,
            lore_path=lore_tree,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            builder.build_lore_index()

        with open(output_dir / "lore_metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        for entry in metadata:
            assert "chunk_id" in entry
            assert "text" in entry
            assert entry["source_type"] in (
                "character",
                "glossary",
                "place",
                "synopsis",
            )

    def test_build_info_created(self, dlglist_tree, tmp_path):
        """build_info.json이 생성되는지."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=dlglist_tree,
            lore_path=None,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            builder.build_dialogue_index()

        info_path = output_dir / "dialogue_build_info.json"
        assert info_path.exists()
        with open(info_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        assert "build_time" in info
        assert "total_sentences" in info

    def test_vectors_shape(self, dlglist_tree, tmp_path):
        """벡터 파일의 shape 검증: (N, 1536)."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=dlglist_tree,
            lore_path=None,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            stats = builder.build_dialogue_index()

        vectors = np.load(output_dir / "dialogue_vectors.npy")
        assert vectors.ndim == 2
        assert vectors.shape[0] == stats["total_sentences"]
        assert vectors.shape[1] == 1536


# -- 코사인 유사도 검색 테스트 --


class TestCosineSimilaritySearch:
    def test_basic_search(self):
        """기본 코사인 유사도 검색."""
        # 3개 벡터: 0번과 2번이 유사, 1번은 다름
        vectors = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.9, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        metadata = [
            {"chunk_id": "a", "text": "text_a"},
            {"chunk_id": "b", "text": "text_b"},
            {"chunk_id": "a", "text": "text_c"},  # 같은 청크
        ]

        results = cosine_similarity_search(
            query_vector=query,
            vectors=vectors,
            metadata=metadata,
            top_k=3,
        )

        assert len(results) > 0
        # 첫 번째 결과가 가장 유사한 벡터
        assert results[0]["score"] >= results[-1]["score"]

    def test_parent_chunk_aggregation(self):
        """부모 청크 기준 집계: 같은 chunk_id 문장은 최고 점수로 집계."""
        vectors = np.array(
            [
                [1.0, 0.0, 0.0],  # chunk A, score 1.0
                [0.0, 1.0, 0.0],  # chunk B, score 0.0
                [0.8, 0.2, 0.0],  # chunk A, score ~0.97
                [0.0, 0.9, 0.1],  # chunk B, score ~0.0
            ],
            dtype=np.float32,
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        metadata = [
            {"chunk_id": "A", "text": "s1"},
            {"chunk_id": "B", "text": "s2"},
            {"chunk_id": "A", "text": "s3"},
            {"chunk_id": "B", "text": "s4"},
        ]

        results = cosine_similarity_search(
            query_vector=query,
            vectors=vectors,
            metadata=metadata,
            top_k=2,
            aggregate_by_chunk=True,
        )

        # 집계 결과: chunk A가 1등 (점수 1.0), chunk B가 2등
        assert len(results) == 2
        assert results[0]["chunk_id"] == "A"
        assert results[1]["chunk_id"] == "B"

    def test_top_k_limits(self):
        """top_k가 결과 수를 제한하는지."""
        n = 10
        vectors = np.random.randn(n, 3).astype(np.float32)
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        metadata = [{"chunk_id": f"c{i}", "text": f"t{i}"} for i in range(n)]

        results = cosine_similarity_search(
            query_vector=query,
            vectors=vectors,
            metadata=metadata,
            top_k=3,
        )
        assert len(results) <= 3

    def test_empty_vectors(self):
        """빈 벡터에 대해 빈 결과 반환."""
        vectors = np.zeros((0, 3), dtype=np.float32)
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        results = cosine_similarity_search(
            query_vector=query,
            vectors=vectors,
            metadata=[],
            top_k=5,
        )
        assert results == []


# -- load_embedding_index 테스트 --


class TestLoadEmbeddingIndex:
    def test_load_saved_index(self, dlglist_tree, tmp_path):
        """저장된 인덱스를 로드하여 검색 가능한지."""
        output_dir = tmp_path / "embeddings"
        builder = EmbeddingIndexBuilder(
            narrative_path=dlglist_tree,
            lore_path=None,
            output_dir=output_dir,
        )

        with patch.object(
            builder._cache, "get_embeddings", side_effect=_mock_get_embeddings
        ):
            builder.build_dialogue_index()

        vectors, metadata = load_embedding_index(output_dir, "dialogue")
        assert isinstance(vectors, np.ndarray)
        assert len(metadata) == vectors.shape[0]

    def test_load_nonexistent_raises(self, tmp_path):
        """존재하지 않는 인덱스 로드 시 에러."""
        with pytest.raises(FileNotFoundError):
            load_embedding_index(tmp_path / "nope", "dialogue")
