"""시간 범위 검색 — 바이너리 서치로 대용량 파일을 지원한다."""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from pathlib import Path

from parsers import LogEntry, get_parser

# 바이너리 서치 임계값 (10 MB)
_BINARY_SEARCH_THRESHOLD = 10 * 1024 * 1024

# 바이너리 서치 최대 반복 횟수 (안전 장치, log2(1TB) < 40)
_MAX_BINARY_ITERATIONS = 60


def _binary_search_position(
    file_path: Path,
    target_time: datetime,
    component: str,
) -> int:
    """대용량 파일에서 target_time 근처의 바이트 위치를 바이너리 서치로 찾는다.

    바이너리 모드로 열어서 정확한 바이트 오프셋을 사용한다.
    정확한 위치가 아니라 '근사 위치'를 반환한다.
    호출자는 이 위치에서 포워드 스캔해야 한다.
    """
    parser = get_parser(component)
    size = file_path.stat().st_size

    low = 0
    high = size
    best = 0
    iterations = 0

    with open(file_path, "rb") as fh:
        while low < high and iterations < _MAX_BINARY_ITERATIONS:
            iterations += 1
            mid = (low + high) // 2
            fh.seek(mid)

            # 줄 경계로 이동 (중간에서 시작하면 잘린 줄일 수 있으므로)
            if mid > 0:
                fh.readline()  # 잘린 줄 버리기

            pos_before = fh.tell()
            raw_line = fh.readline()
            if not raw_line:
                high = mid
                continue

            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            entry = parser.parse(line, component, 0)
            if entry and entry.timestamp:
                if entry.timestamp < target_time:
                    best = pos_before
                    low = mid + 1
                else:
                    high = mid
            else:
                # 파싱 실패 시 앞으로 전진
                low = mid + 1

    return max(0, best)


def search_file(
    file_path: Path,
    component: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    level: str | None = None,
    pattern: re.Pattern[str] | None = None,
    tail: int | None = None,
) -> list[LogEntry]:
    """단일 로그 파일에서 조건에 맞는 엔트리를 검색한다.

    Args:
        file_path: 로그 파일 경로
        component: 컴포넌트 이름
        start_time: 시작 시각 (이상)
        end_time: 종료 시각 (이하)
        level: 로그 레벨 필터 (ERROR 이상 등)
        pattern: 메시지 정규식 패턴
        tail: 마지막 N건만 반환
    """
    if not file_path.exists():
        return []

    parser = get_parser(component)
    level_filter = _level_set(level) if level else None

    # 대용량 파일 + 시작 시간 지정 시 바이너리 서치
    seek_pos = 0
    file_size = file_path.stat().st_size
    if start_time and file_size >= _BINARY_SEARCH_THRESHOLD:
        seek_pos = _binary_search_position(file_path, start_time, component)

    results: list[LogEntry] | deque[LogEntry]
    if tail:
        results = deque(maxlen=tail)
    else:
        results = []

    # 바이너리 서치로 seek한 경우 바이너리 모드로 열어야 함 (Windows CRLF 문제 방지)
    # seek하지 않는 경우도 일관성을 위해 바이너리 모드 사용
    with open(file_path, "rb") as fh:
        if seek_pos > 0:
            fh.seek(seek_pos)
            fh.readline()  # 잘린 줄 버리기

        # NOTE: seek 후 line_number는 근사값 (seek 이전 줄 수를 모름)
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            if not line:
                continue

            entry = parser.parse(line, component, line_number)
            if entry is None:
                continue

            # 시간 범위 필터
            if entry.timestamp:
                if start_time and entry.timestamp < start_time:
                    continue
                # ASSUMPTION: 로그는 시간순이므로 end_time 초과 시 조기 종료.
                # 순서가 뒤바뀐 엔트리는 누락될 수 있음.
                if end_time and entry.timestamp > end_time:
                    break

            # 레벨 필터
            if level_filter and entry.level not in level_filter:
                continue

            # 패턴 필터
            if pattern and not pattern.search(entry.message):
                continue

            results.append(entry)

    return list(results)


_LEVEL_HIERARCHY = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _level_set(min_level: str) -> set[str]:
    """min_level 이상의 레벨 집합을 반환한다."""
    min_level = min_level.upper()
    if min_level not in _LEVEL_HIERARCHY:
        return {min_level}
    idx = _LEVEL_HIERARCHY.index(min_level)
    return set(_LEVEL_HIERARCHY[idx:])
