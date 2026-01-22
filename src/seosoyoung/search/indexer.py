"""Whoosh indexer for dialogue data."""

import sys
from pathlib import Path
from typing import Optional

import yaml
from whoosh.index import create_in, open_dir, exists_in

from .schema import dialogue_schema
from .reference import DialogueReferenceMap


class DialogueIndexer:
    """dlglist YAML 파일을 Whoosh 인덱스로 변환."""

    def __init__(
        self,
        narrative_path: str | Path,
        index_path: str | Path
    ):
        """
        Args:
            narrative_path: eb_narrative/narrative 경로
            index_path: 인덱스 저장 경로
        """
        self.narrative_path = Path(narrative_path)
        self.dlglist_path = self.narrative_path / "dlglist"
        self.index_path = Path(index_path)
        self._ref_map: Optional[DialogueReferenceMap] = None

    def create_index(self, force: bool = False):
        """인덱스 생성 또는 열기.

        Args:
            force: True면 기존 인덱스 삭제 후 재생성
        """
        self.index_path.mkdir(parents=True, exist_ok=True)

        if force or not exists_in(str(self.index_path)):
            self.ix = create_in(str(self.index_path), dialogue_schema)
        else:
            self.ix = open_dir(str(self.index_path))

        return self.ix

    def index_all(self, force: bool = False) -> dict:
        """모든 dlglist 파일 인덱싱.

        Args:
            force: True면 기존 인덱스 삭제 후 재생성

        Returns:
            통계 정보 dict
        """
        # 역참조 맵 빌드
        print("Building reference map...")
        self._ref_map = DialogueReferenceMap(self.narrative_path)
        self._ref_map.build()
        ref_stats = self._ref_map.get_stats()
        print(f"  Reference map: {ref_stats['total_dlgids']} dlgIds, "
              f"{ref_stats['unique_labels']} labels, "
              f"{ref_stats['unique_triggers']} triggers")

        self.create_index(force=force)
        writer = self.ix.writer()

        stats = {
            "files": 0,
            "dialogues": 0,
            "with_metadata": 0,
            "errors": []
        }

        if not self.dlglist_path.exists():
            stats["errors"].append(f"dlglist path not found: {self.dlglist_path}")
            return stats

        for yaml_file in self.dlglist_path.glob("*.yaml"):
            try:
                file_count, meta_count = self._index_file(writer, yaml_file)
                stats["files"] += 1
                stats["dialogues"] += file_count
                stats["with_metadata"] += meta_count
            except Exception as e:
                stats["errors"].append(f"{yaml_file.name}: {e}")

        writer.commit()
        return stats

    def _index_file(self, writer, yaml_file: Path) -> tuple[int, int]:
        """개별 YAML 파일 인덱싱.

        Returns:
            (인덱싱된 대사 수, 메타데이터가 있는 대사 수)
        """
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "dialogues" not in data:
            return 0, 0

        count = 0
        meta_count = 0
        for dlg in data["dialogues"]:
            dlgId = dlg.get("dlgId", "")
            if not dlgId:
                continue

            # 역참조 맵에서 메타데이터 조회
            labels = ""
            revision = ""
            acts = ""
            trigger = ""

            if self._ref_map:
                meta = self._ref_map.get(dlgId)
                if meta:
                    meta_count += 1
                    labels = ",".join(sorted(meta.labels)) if meta.labels else ""
                    # 모든 리비전 저장 (쉼표로 구분)
                    revision = ",".join(sorted(meta.revisions)) if meta.revisions else ""
                    acts = ",".join(sorted(meta.acts)) if meta.acts else ""
                    # 트리거가 여러 개일 수 있으나 첫 번째만 사용
                    trigger = sorted(meta.triggers)[0] if meta.triggers else ""

            writer.add_document(
                dlgId=dlgId,
                speaker=dlg.get("speaker", ""),
                text_kr=dlg.get("kr", ""),
                text_en=dlg.get("en", ""),
                hash=dlg.get("hash", ""),
                source_file=yaml_file.name,
                labels=labels,
                revision=revision,
                acts=acts,
                trigger=trigger
            )
            count += 1

        return count, meta_count


def get_default_paths() -> tuple[Path, Path]:
    """기본 경로 반환.

    Returns:
        (narrative_path, index_path) 튜플
    """
    workspace = Path.cwd()
    narrative_path = workspace / "eb_narrative" / "narrative"
    index_path = workspace / "internal" / "index" / "dialogues"
    return narrative_path, index_path


def build_index(
    narrative_path: str | Path = None,
    index_path: str | Path = None,
    force: bool = False
) -> dict:
    """인덱스 빌드 CLI 진입점.

    Args:
        narrative_path: eb_narrative/narrative 경로 (None이면 기본값)
        index_path: 인덱스 저장 경로 (None이면 기본값)
        force: True면 기존 인덱스 삭제 후 재생성

    Returns:
        통계 정보 dict
    """
    if narrative_path is None or index_path is None:
        default_narrative, default_index = get_default_paths()
        narrative_path = narrative_path or default_narrative
        index_path = index_path or default_index

    indexer = DialogueIndexer(narrative_path, index_path)

    print(f"Indexing dialogues from: {indexer.dlglist_path}")
    print(f"Index path: {indexer.index_path}")

    stats = indexer.index_all(force=force)

    print(f"\nIndexing complete!")
    print(f"  Files processed: {stats['files']}")
    print(f"  Dialogues indexed: {stats['dialogues']}")
    print(f"  With metadata: {stats['with_metadata']}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"  - {err}")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build Whoosh index for dialogue search")
    parser.add_argument("--narrative-path", help="eb_narrative/narrative path")
    parser.add_argument("--index-path", help="Index storage path")
    parser.add_argument("--force", "-f", action="store_true", help="Force rebuild index")

    args = parser.parse_args()
    build_index(args.narrative_path, args.index_path, force=args.force)
