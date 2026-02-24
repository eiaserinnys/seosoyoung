"""통합 빌드 스크립트 — Whoosh + 임베딩 인덱스를 한 번에 빌드.

Usage:
    python -m seosoyoung.search.build                    # 전체 빌드
    python -m seosoyoung.search.build --whoosh-only      # Whoosh만
    python -m seosoyoung.search.build --embedding-only   # 임베딩만
    python -m seosoyoung.search.build --force            # 강제 재빌드
"""

import json
import sys
from pathlib import Path

from .indexer import DialogueIndexer
from .lore_indexer import LoreIndexer
from .embedding_index import EmbeddingIndexBuilder


def build_whoosh(
    narrative_path: str | Path,
    lore_path: str | Path,
    index_root: str | Path,
    force: bool = False,
) -> dict:
    """Whoosh 인덱스 빌드 (대사 + 로어).

    narrative_path는 eb_narrative 루트 (예: ./eb_narrative).
    DialogueIndexer는 내부적으로 narrative_path/dlglist를 보므로
    narrative/dlglist 구조에 맞게 narrative/ 서브디렉토리를 전달한다.
    """
    index_root = Path(index_root)
    narrative_path = Path(narrative_path)

    result = {}

    # DialogueIndexer는 narrative_path/dlglist를 탐색
    # 실제 구조: eb_narrative/narrative/dlglist
    whoosh_narrative = narrative_path / "narrative"
    if not (whoosh_narrative / "dlglist").exists():
        # fallback: narrative_path 자체에 dlglist가 있는 경우 (테스트 등)
        whoosh_narrative = narrative_path

    dlg_index_path = index_root / "dialogues"
    dlg_indexer = DialogueIndexer(whoosh_narrative, dlg_index_path)
    result["dialogue"] = dlg_indexer.index_all(force=force)

    # 로어 인덱스
    lore_index_path = index_root / "lore"
    lore_indexer = LoreIndexer(lore_path, lore_index_path)
    result["lore"] = lore_indexer.index_all(force=force)

    return result


def build_embeddings(
    narrative_path: str | Path,
    lore_path: str | Path,
    index_root: str | Path,
    cache_path: str | Path | None = None,
    api_key: str | None = None,
) -> dict:
    """임베딩 인덱스 빌드 (대사 + 로어)."""
    index_root = Path(index_root)
    emb_dir = index_root / "embeddings"

    if cache_path is None:
        cache_path = index_root / "embedding_cache.json"

    builder = EmbeddingIndexBuilder(
        narrative_path=narrative_path,
        lore_path=lore_path,
        output_dir=emb_dir,
        cache_path=cache_path,
        api_key=api_key,
    )

    result = {}
    result["dialogue"] = builder.build_dialogue_index()
    result["lore"] = builder.build_lore_index()

    return result


def build_all(
    narrative_path: str | Path,
    lore_path: str | Path,
    index_root: str | Path,
    force: bool = False,
    whoosh_only: bool = False,
    embedding_only: bool = False,
    cache_path: str | Path | None = None,
    api_key: str | None = None,
) -> dict:
    """Whoosh + 임베딩 인덱스 통합 빌드.

    Args:
        narrative_path: eb_narrative 경로 (narrative/ 포함)
        lore_path: eb_lore 경로 (content/ 포함)
        index_root: 인덱스 루트 디렉토리
        force: 강제 재빌드
        whoosh_only: Whoosh만 빌드
        embedding_only: 임베딩만 빌드
        cache_path: 임베딩 캐시 경로
        api_key: OpenAI API key

    Returns:
        빌드 결과 통계
    """
    result = {}

    if not embedding_only:
        result["whoosh"] = build_whoosh(
            narrative_path=narrative_path,
            lore_path=lore_path,
            index_root=index_root,
            force=force,
        )

    if not whoosh_only:
        result["embedding"] = build_embeddings(
            narrative_path=narrative_path,
            lore_path=lore_path,
            index_root=index_root,
            cache_path=cache_path,
            api_key=api_key,
        )

    return result


def main():
    """CLI 진입점."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build search indices (Whoosh + embedding)",
    )
    parser.add_argument(
        "--narrative-path",
        default="./eb_narrative",
        help="eb_narrative path (default: ./eb_narrative)",
    )
    parser.add_argument(
        "--lore-path",
        default="./eb_lore",
        help="eb_lore path (default: ./eb_lore)",
    )
    parser.add_argument(
        "--index-root",
        default="./.local/index",
        help="Index root directory (default: ./.local/index)",
    )
    parser.add_argument("--force", action="store_true", help="Force rebuild")
    parser.add_argument(
        "--whoosh-only", action="store_true", help="Build Whoosh only"
    )
    parser.add_argument(
        "--embedding-only", action="store_true", help="Build embeddings only"
    )
    parser.add_argument("--cache-path", help="Embedding cache path")
    parser.add_argument("--api-key", help="OpenAI API key")

    args = parser.parse_args()

    stats = build_all(
        narrative_path=args.narrative_path,
        lore_path=args.lore_path,
        index_root=args.index_root,
        force=args.force,
        whoosh_only=args.whoosh_only,
        embedding_only=args.embedding_only,
        cache_path=args.cache_path,
        api_key=args.api_key,
    )

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
