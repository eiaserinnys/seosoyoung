"""대화 구조 파일에서 dlgId → 메타데이터 역참조 맵 생성."""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import yaml


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
        """
        Args:
            narrative_path: eb_narrative/narrative 경로
        """
        self.narrative_path = Path(narrative_path)
        self._ref_map: dict[str, DialogueMetadata] = {}

    def build(self) -> dict[str, DialogueMetadata]:
        """모든 구조 파일을 스캔하여 역참조 맵 생성.

        Returns:
            dlgId → DialogueMetadata 매핑
        """
        self._ref_map = {}

        # _rev1, _rev2 스캔
        for rev_folder in ["_rev1", "_rev2"]:
            rev_path = self.narrative_path / rev_folder
            if rev_path.exists():
                revision = rev_folder  # "_rev1" 또는 "_rev2"
                self._scan_revision(rev_path, revision)

        return self._ref_map

    def _scan_revision(self, rev_path: Path, revision: str):
        """리비전 폴더 스캔.

        Args:
            rev_path: _rev1 또는 _rev2 경로
            revision: "_rev1" 또는 "_rev2"
        """
        for yaml_file in rev_path.rglob("*.yaml"):
            try:
                self._process_structure_file(yaml_file, revision)
            except Exception as e:
                # 에러는 무시하고 계속 진행
                pass

    def _process_structure_file(self, yaml_file: Path, revision: str):
        """개별 구조 파일 처리.

        Args:
            yaml_file: YAML 파일 경로
            revision: "_rev1" 또는 "_rev2"
        """
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return

        # 파일 경로에서 액트 추출
        acts = self._extract_acts_from_path(yaml_file, revision)

        # 파일 레벨의 act 필드가 있으면 추가
        if "act" in data and isinstance(data["act"], list):
            for act in data["act"]:
                acts.add(act.lower())

        # dialogues 배열 처리
        dialogues = data.get("dialogues", [])
        if not isinstance(dialogues, list):
            return

        for dlg_entry in dialogues:
            if not isinstance(dlg_entry, dict):
                continue

            label = dlg_entry.get("label", "")
            trigger = dlg_entry.get("trigger", "")

            # dlgId 수집 위치들
            dlgid_locations = [
                "dialogue",      # 메인 대사
                "pre_bk",        # 프리 바크
                "post_bk",       # 포스트 바크
            ]

            for loc in dlgid_locations:
                self._collect_dlgids(
                    dlg_entry.get(loc, []),
                    label=label,
                    revision=revision,
                    acts=acts,
                    trigger=trigger
                )

            # bk_var 처리 (변형 바크)
            bk_var = dlg_entry.get("bk_var", [])
            if isinstance(bk_var, list):
                for var_entry in bk_var:
                    if isinstance(var_entry, dict) and "bk" in var_entry:
                        self._collect_dlgids(
                            var_entry["bk"],
                            label=label,
                            revision=revision,
                            acts=acts,
                            trigger=trigger
                        )

    def _extract_acts_from_path(self, yaml_file: Path, revision: str) -> set[str]:
        """파일 경로에서 액트 정보 추출.

        Args:
            yaml_file: YAML 파일 경로
            revision: "_rev1" 또는 "_rev2"

        Returns:
            액트 이름 집합 (소문자)
        """
        acts = set()
        parts = yaml_file.parts

        # 경로에서 act* 패턴 찾기
        for part in parts:
            part_lower = part.lower()
            if part_lower.startswith("act") or part_lower.startswith("_act"):
                # "_act0" → "act0", "act1" → "act1"
                act_name = part_lower.lstrip("_")
                acts.add(act_name)

        return acts

    def _collect_dlgids(
        self,
        items: list,
        label: str,
        revision: str,
        acts: set[str],
        trigger: str
    ):
        """dlgId 항목 수집 및 메타데이터 기록.

        Args:
            items: dlgId를 포함한 항목 리스트
            label: 레이블 이름
            revision: "_rev1" 또는 "_rev2"
            acts: 액트 집합
            trigger: 트리거 이름
        """
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

            # 메타데이터 추가
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
        """dlgId에 대한 메타데이터 조회.

        Args:
            dlgId: 대사 ID

        Returns:
            DialogueMetadata 또는 None
        """
        return self._ref_map.get(dlgId)

    def get_stats(self) -> dict:
        """역참조 맵 통계."""
        if not self._ref_map:
            return {
                "total_dlgids": 0,
                "unique_labels": 0,
                "unique_triggers": 0
            }

        all_labels = set()
        all_triggers = set()
        for meta in self._ref_map.values():
            all_labels.update(meta.labels)
            all_triggers.update(meta.triggers)

        return {
            "total_dlgids": len(self._ref_map),
            "unique_labels": len(all_labels),
            "unique_triggers": len(all_triggers)
        }


def build_reference_map(narrative_path: str | Path = None) -> DialogueReferenceMap:
    """역참조 맵 빌드 헬퍼.

    Args:
        narrative_path: eb_narrative/narrative 경로

    Returns:
        빌드된 DialogueReferenceMap
    """
    if narrative_path is None:
        # 기본 경로: workspace/eb_narrative/narrative
        narrative_path = Path.cwd() / "eb_narrative" / "narrative"

    ref_map = DialogueReferenceMap(narrative_path)
    ref_map.build()
    return ref_map


if __name__ == "__main__":
    import json

    ref_map = build_reference_map()
    stats = ref_map.get_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    # 샘플 출력
    print("\n샘플 메타데이터:")
    for i, (dlgId, meta) in enumerate(ref_map._ref_map.items()):
        if i >= 5:
            break
        print(f"  {dlgId}:")
        print(f"    labels: {meta.labels}")
        print(f"    revisions: {meta.revisions}")
        print(f"    acts: {meta.acts}")
        print(f"    triggers: {meta.triggers}")
