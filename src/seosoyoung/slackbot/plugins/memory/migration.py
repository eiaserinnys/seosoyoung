"""OM 마크다운 → JSON 마이그레이션

런타임 memory/ 디렉토리의 .md 파일들을 .json으로 일괄 변환합니다.

사용:
    from seosoyoung.slackbot.plugins.memory.migration import migrate_memory_dir
    report = migrate_memory_dir("/path/to/memory", dry_run=True)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from seosoyoung.slackbot.plugins.memory.store import parse_md_observations, parse_md_persistent

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    """마이그레이션 결과 보고서"""

    observations_converted: list[str] = field(default_factory=list)
    persistent_converted: bool = False
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def total_converted(self) -> int:
        return len(self.observations_converted) + (1 if self.persistent_converted else 0)

    def summary(self) -> str:
        mode = "[DRY RUN] " if self.dry_run else ""
        lines = [
            f"{mode}마이그레이션 완료",
            f"  관찰 로그 변환: {len(self.observations_converted)}건",
            f"  장기 기억 변환: {'예' if self.persistent_converted else '아니오'}",
            f"  건너뜀: {len(self.skipped)}건",
            f"  오류: {len(self.errors)}건",
        ]
        return "\n".join(lines)


def _backup_md(md_path: Path) -> Path:
    """원본 .md를 .md.bak으로 백업합니다."""
    bak_path = md_path.with_suffix(".md.bak")
    bak_path.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return bak_path


def migrate_observations(observations_dir: Path, dry_run: bool = False) -> MigrationReport:
    """observations/ 디렉토리의 .md 파일을 .json으로 변환합니다.

    변환 대상: {thread_ts}.md → {thread_ts}.json
    이미 .json이 존재하면 건너뜁니다.
    """
    report = MigrationReport(dry_run=dry_run)

    if not observations_dir.exists():
        return report

    for md_path in sorted(observations_dir.glob("*.md")):
        stem = md_path.stem

        # .new.md 파일도 처리
        if stem.endswith(".new"):
            json_path = observations_dir / f"{stem}.json"
        else:
            json_path = md_path.with_suffix(".json")

        if json_path.exists():
            report.skipped.append(str(md_path.name))
            continue

        try:
            md_text = md_path.read_text(encoding="utf-8")
            items = parse_md_observations(md_text)

            if dry_run:
                logger.info(
                    f"[DRY RUN] {md_path.name} → {json_path.name} ({len(items)} items)"
                )
            else:
                _backup_md(md_path)
                json_path.write_text(
                    json.dumps(items, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                md_path.unlink()
                logger.info(
                    f"변환 완료: {md_path.name} → {json_path.name} ({len(items)} items)"
                )

            report.observations_converted.append(md_path.name)

        except Exception as e:
            report.errors.append(f"{md_path.name}: {e}")
            logger.error(f"변환 실패: {md_path.name}: {e}")

    return report


def migrate_persistent(persistent_dir: Path, dry_run: bool = False) -> bool:
    """persistent/recent.md → recent.json 변환.

    Returns:
        True: 변환 수행됨, False: 변환 불필요
    """
    md_path = persistent_dir / "recent.md"
    json_path = persistent_dir / "recent.json"

    if not md_path.exists():
        return False

    if json_path.exists():
        logger.info("persistent/recent.json이 이미 존재하여 건너뜁니다.")
        return False

    try:
        md_text = md_path.read_text(encoding="utf-8")
        items = parse_md_persistent(md_text)

        if dry_run:
            logger.info(
                f"[DRY RUN] recent.md → recent.json ({len(items)} items)"
            )
        else:
            _backup_md(md_path)
            json_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            md_path.unlink()
            logger.info(f"변환 완료: recent.md → recent.json ({len(items)} items)")

        return True

    except Exception as e:
        logger.error(f"persistent 변환 실패: {e}")
        return False


def migrate_memory_dir(base_dir: str | Path, dry_run: bool = False) -> MigrationReport:
    """memory/ 디렉토리 전체를 마이그레이션합니다.

    Args:
        base_dir: memory/ 디렉토리 경로
        dry_run: True면 실제 변환 없이 대상만 출력

    Returns:
        MigrationReport
    """
    base = Path(base_dir)

    if not base.exists():
        report = MigrationReport(dry_run=dry_run)
        report.errors.append(f"디렉토리가 존재하지 않습니다: {base}")
        return report

    # observations/
    observations_dir = base / "observations"
    report = migrate_observations(observations_dir, dry_run=dry_run)
    report.dry_run = dry_run

    # persistent/
    persistent_dir = base / "persistent"
    report.persistent_converted = migrate_persistent(persistent_dir, dry_run=dry_run)

    return report
