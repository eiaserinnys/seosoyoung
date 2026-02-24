"""OM 마크다운 → JSON 마이그레이션 CLI

런타임 memory/ 디렉토리의 .md 파일들을 .json 항목 배열로 일괄 변환합니다.

사용:
    python scripts/migrate_om_to_json.py --base-dir /path/to/memory
    python scripts/migrate_om_to_json.py --base-dir /path/to/memory --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

# seosoyoung 패키지가 PYTHONPATH에 있어야 합니다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seosoyoung.slackbot.memory.migration import migrate_memory_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OM 마크다운 → JSON 마이그레이션",
    )
    parser.add_argument(
        "--base-dir",
        required=True,
        help="memory/ 디렉토리 경로 (observations/, persistent/ 포함)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변환 없이 대상만 출력",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        logging.error(f"디렉토리가 존재하지 않습니다: {base_dir}")
        return 1

    report = migrate_memory_dir(base_dir, dry_run=args.dry_run)
    print()
    print(report.summary())

    if report.errors:
        print("\n오류 목록:")
        for err in report.errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
