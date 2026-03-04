"""세션 경계 탐색 — 기동/종료 마커를 기반으로 세션 세그먼트를 식별한다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from parsers import LogEntry, get_parser


@dataclass(frozen=True, slots=True)
class SessionSegment:
    start_time: datetime
    end_time: datetime | None
    start_marker: str
    end_marker: str | None
    exit_code: int | None
    component: str


# 컴포넌트별 시작/종료 마커 정의
@dataclass(frozen=True, slots=True)
class _MarkerDef:
    start_patterns: tuple[re.Pattern[str], ...]
    end_patterns: tuple[re.Pattern[str], ...]


_MARKER_DEFS: dict[str, _MarkerDef] = {
    "bot": _MarkerDef(
        start_patterns=(
            re.compile(r"SeoSoyoung 봇을 시작합니다"),
        ),
        end_patterns=(
            re.compile(r"Bolt app is running!"),
        ),
    ),
    "watchdog": _MarkerDef(
        start_patterns=(
            re.compile(r"supervisor 감시 시작"),
            re.compile(r"supervisor 시작"),
        ),
        end_patterns=(
            re.compile(r"supervisor 종료: exit=(\d+)"),
            re.compile(r"정상 종료"),
        ),
    ),
    "supervisor": _MarkerDef(
        start_patterns=(
            re.compile(r"supervisor 시작"),
            re.compile(r"={5,}"),
        ),
        end_patterns=(
            re.compile(r"supervisor 종료"),
            re.compile(r"전체 종료"),
        ),
    ),
    "soulstream-server": _MarkerDef(
        start_patterns=(
            re.compile(r"Soulstream starting"),
        ),
        end_patterns=(
            re.compile(r"Soulstream shutdown|Soulstream stopped"),
        ),
    ),
}

_EXIT_CODE_RE = re.compile(r"exit=(\d+)")


def find_segments(
    file_path: Path,
    component: str,
    *,
    last: int | None = None,
) -> list[SessionSegment]:
    """로그 파일에서 세션 세그먼트를 식별한다.

    Args:
        file_path: 로그 파일 경로
        component: 컴포넌트 이름
        last: 최근 N개 세그먼트만 반환
    """
    if not file_path.exists():
        return []

    marker_def = _MARKER_DEFS.get(component)
    if marker_def is None:
        # 마커 정의가 없는 컴포넌트는 빈 목록 반환
        return []

    parser = get_parser(component)
    segments: list[SessionSegment] = []
    current_start: datetime | None = None
    current_start_marker: str = ""

    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.rstrip("\n\r")
            if not line:
                continue

            entry = parser.parse(line, component, line_number)
            if entry is None or entry.timestamp is None:
                continue

            # 시작 마커 체크
            is_start = False
            for sp in marker_def.start_patterns:
                if sp.search(entry.message):
                    if current_start is not None:
                        # 이전 세션이 종료되지 않은 채 새 세션 시작
                        segments.append(
                            SessionSegment(
                                start_time=current_start,
                                end_time=entry.timestamp,
                                start_marker=current_start_marker,
                                end_marker=None,
                                exit_code=None,
                                component=component,
                            )
                        )
                    current_start = entry.timestamp
                    current_start_marker = entry.message
                    is_start = True
                    break

            # 종료 마커 체크 (시작 마커와 상호 배타)
            if not is_start and current_start is not None:
                for ep in marker_def.end_patterns:
                    if ep.search(entry.message):
                        exit_code = None
                        exit_match = _EXIT_CODE_RE.search(entry.message)
                        if exit_match:
                            exit_code = int(exit_match.group(1))
                        segments.append(
                            SessionSegment(
                                start_time=current_start,
                                end_time=entry.timestamp,
                                start_marker=current_start_marker,
                                end_marker=entry.message,
                                exit_code=exit_code,
                                component=component,
                            )
                        )
                        current_start = None
                        current_start_marker = ""
                        break

    # 마지막 세션이 아직 열려 있으면 추가
    if current_start is not None:
        segments.append(
            SessionSegment(
                start_time=current_start,
                end_time=None,
                start_marker=current_start_marker,
                end_marker=None,
                exit_code=None,
                component=component,
            )
        )

    if last is not None:
        segments = segments[-last:]

    return segments
