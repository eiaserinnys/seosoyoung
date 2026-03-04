"""슬랙 thread_ts → 로그 상관관계 — 스레드 시점 전후의 로그를 수집한다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from parsers import LogEntry
from scanner import get_sessions_dir, scan_logs
from searcher import search_file


@dataclass(frozen=True, slots=True)
class ContextResult:
    thread_time: datetime
    start_time: datetime
    end_time: datetime
    session_file: Path | None
    session_info: dict | None
    entries: list[LogEntry]


def thread_ts_to_datetime(thread_ts: str) -> datetime:
    """슬랙 thread_ts (예: '1772584610.882089')를 datetime으로 변환한다."""
    return datetime.fromtimestamp(float(thread_ts))


def find_session_file(thread_ts: str) -> Path | None:
    """thread_ts에 해당하는 세션 파일을 찾는다.

    세션 파일명: session_{ts_underscore}.json
    예: session_1772584610_882089.json
    """
    ts_underscore = thread_ts.replace(".", "_")
    session_file = get_sessions_dir() / f"session_{ts_underscore}.json"
    if session_file.exists():
        return session_file
    return None


def load_session_info(session_file: Path) -> dict | None:
    """세션 파일에서 유용한 정보를 로드한다."""
    try:
        with open(session_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def search_context(
    thread_ts: str,
    *,
    window_minutes: int = 5,
    component: str | None = None,
    level: str | None = None,
    pattern: str | None = None,
) -> ContextResult:
    """thread_ts 전후 window_minutes 내의 로그를 수집한다."""
    thread_time = thread_ts_to_datetime(thread_ts)
    start_time = thread_time - timedelta(minutes=window_minutes)
    end_time = thread_time + timedelta(minutes=window_minutes)

    # 세션 파일 조회
    session_file = find_session_file(thread_ts)
    session_info = load_session_info(session_file) if session_file else None

    # 로그 파일 스캔
    log_files = scan_logs(component=component)

    compiled_pattern = re.compile(pattern) if pattern else None
    all_entries: list[LogEntry] = []

    for lf in log_files:
        # 날짜 힌트가 있고 범위 밖이면 스킵
        if lf.date_hint:
            if lf.date_hint < start_time.date() or lf.date_hint > end_time.date():
                continue

        # 빈 파일 스킵
        if lf.size_bytes == 0:
            continue

        entries = search_file(
            lf.path,
            lf.component,
            start_time=start_time,
            end_time=end_time,
            level=level,
            pattern=compiled_pattern,
        )
        all_entries.extend(entries)

    # 시간순 정렬
    all_entries.sort(key=lambda e: (e.timestamp or datetime.min, e.line_number))

    return ContextResult(
        thread_time=thread_time,
        start_time=start_time,
        end_time=end_time,
        session_file=session_file,
        session_info=session_info,
        entries=all_entries,
    )
