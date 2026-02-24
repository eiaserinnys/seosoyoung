"""Dialogue indexer — dlglist YAML → Whoosh index.

`.tools/build-dialogue-index/main.py`에서 이전된 인덱서.
DialogueReferenceMap으로 대화 구조 파일에서 dlgId 메타데이터를 수집한 뒤,
DialogueIndexer가 dlglist YAML을 Whoosh 인덱스로 변환한다.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from whoosh.index import create_in, open_dir, exists_in

from .schema import dialogue_schema


@dataclass
class DialogueMetadata:
    """dlgId에 대한 메타데이터."""
    labels: set[str] = field(default_factory=set)
    revisions: set[str] = field(default_factory=set)
    acts: set[str] = field(default_factory=set)
    triggers: set[str] = field(default_factory=set)


class DialogueReferenceMap:
    """대화 구조 파일을 스캔하여 dlgId → 메타데이터 역참조 맵 생성."""

    def __init__(self, narrative_path: str | Path):
        self.narrative_path = Path(narrative_path)
        self._ref_map: dict[str, DialogueMetadata] = {}

    def build(self) -> dict[str, DialogueMetadata]:
        """모든 구조 파일을 스캔하여 역참조 맵 생성."""
        self._ref_map = {}

        for rev_folder in ["_rev1", "_rev2"]:
            rev_path = self.narrative_path / rev_folder
            if rev_path.exists():
                self._scan_revision(rev_path, rev_folder)

        return self._ref_map

    def _scan_revision(self, rev_path: Path, revision: str):
        """리비전 폴더 스캔."""
        for yaml_file in rev_path.rglob("*.yaml"):
            try:
                self._process_structure_file(yaml_file, revision)
            except Exception:
                pass

    def _process_structure_file(self, yaml_file: Path, revision: str):
        """개별 구조 파일 처리."""
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return

        acts = self._extract_acts_from_path(yaml_file, revision)

        if "act" in data and isinstance(data["act"], list):
            for act in data["act"]:
                acts.add(act.lower())

        dialogues = data.get("dialogues", [])
        if not isinstance(dialogues, list):
            return

        for dlg_entry in dialogues:
            if not isinstance(dlg_entry, dict):
                continue

            label = dlg_entry.get("label", "")
            trigger = dlg_entry.get("trigger", "")

            for loc in ["dialogue", "pre_bk", "post_bk"]:
                self._collect_dlgids(
                    dlg_entry.get(loc, []),
                    label=label,
                    revision=revision,
                    acts=acts,
                    trigger=trigger,
                )

            bk_var = dlg_entry.get("bk_var", [])
            if isinstance(bk_var, list):
                for var_entry in bk_var:
                    if isinstance(var_entry, dict) and "bk" in var_entry:
                        self._collect_dlgids(
                            var_entry["bk"],
                            label=label,
                            revision=revision,
                            acts=acts,
                            trigger=trigger,
                        )

    def _extract_acts_from_path(self, yaml_file: Path, revision: str) -> set[str]:
        """파일 경로에서 액트 정보 추출."""
        acts: set[str] = set()
        for part in yaml_file.parts:
            part_lower = part.lower()
            if part_lower.startswith("act") or part_lower.startswith("_act"):
                act_name = part_lower.lstrip("_")
                acts.add(act_name)
        return acts

    def _collect_dlgids(
        self,
        items: list,
        label: str,
        revision: str,
        acts: set[str],
        trigger: str,
    ):
        """dlgId 항목 수집 및 메타데이터 기록."""
        if not isinstance(items, list):
            return

        for item in items:
            dlgId = None
            if isinstance(item, dict):
                dlgId = item.get("dlgId")
            elif isinstance(item, str):
                dlgId = item

            if not dlgId:
                continue

            if dlgId not in self._ref_map:
                self._ref_map[dlgId] = DialogueMetadata()

            meta = self._ref_map[dlgId]
            if label:
                meta.labels.add(label)
            meta.revisions.add(revision)
            meta.acts.update(acts)
            if trigger:
                meta.triggers.add(trigger)

    def get(self, dlgId: str) -> Optional[DialogueMetadata]:
        """dlgId에 대한 메타데이터 조회."""
        return self._ref_map.get(dlgId)

    def get_stats(self) -> dict:
        """역참조 맵 통계."""
        if not self._ref_map:
            return {"total_dlgids": 0, "unique_labels": 0, "unique_triggers": 0}

        all_labels: set[str] = set()
        all_triggers: set[str] = set()
        for meta in self._ref_map.values():
            all_labels.update(meta.labels)
            all_triggers.update(meta.triggers)

        return {
            "total_dlgids": len(self._ref_map),
            "unique_labels": len(all_labels),
            "unique_triggers": len(all_triggers),
        }


class DialogueIndexer:
    """dlglist YAML 파일을 Whoosh 인덱스로 변환."""

    def __init__(self, narrative_path: str | Path, index_path: str | Path):
        self.narrative_path = Path(narrative_path)
        self.dlglist_path = self.narrative_path / "dlglist"
        self.index_path = Path(index_path)
        self._ref_map: Optional[DialogueReferenceMap] = None

    def create_index(self, force: bool = False):
        """인덱스 생성 또는 열기."""
        self.index_path.mkdir(parents=True, exist_ok=True)

        if force or not exists_in(str(self.index_path)):
            self.ix = create_in(str(self.index_path), dialogue_schema)
        else:
            self.ix = open_dir(str(self.index_path))

        return self.ix

    def index_all(self, force: bool = False) -> dict:
        """모든 dlglist 파일 인덱싱."""
        self._ref_map = DialogueReferenceMap(self.narrative_path)
        self._ref_map.build()

        self.create_index(force=force)
        writer = self.ix.writer()

        stats = {
            "files": 0,
            "dialogues": 0,
            "with_metadata": 0,
            "errors": [],
        }

        if not self.dlglist_path.exists():
            stats["errors"].append(f"dlglist path not found: {self.dlglist_path}")
            writer.commit()
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
        """개별 YAML 파일 인덱싱."""
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

            labels = ""
            revision = ""
            acts = ""
            trigger = ""

            if self._ref_map:
                meta = self._ref_map.get(dlgId)
                if meta:
                    meta_count += 1
                    labels = ",".join(sorted(meta.labels)) if meta.labels else ""
                    revision = (
                        ",".join(sorted(meta.revisions)) if meta.revisions else ""
                    )
                    acts = ",".join(sorted(meta.acts)) if meta.acts else ""
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
                trigger=trigger,
            )
            count += 1

        return count, meta_count
