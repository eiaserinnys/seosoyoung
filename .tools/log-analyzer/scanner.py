"""파일 탐색 및 메타데이터 — 두 런타임의 로그 파일을 스캔한다."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


def _env_path(name: str) -> Path:
    """환경변수에서 경로를 읽는다. 없으면 즉시 에러."""
    value = os.environ.get(name)
    if value is None:
        raise EnvironmentError(
            f"환경변수 '{name}'이 설정되지 않았습니다. "
            f".env 파일을 확인해주세요."
        )
    return Path(value)


def get_seosoyoung_logs() -> Path:
    return _env_path("LOG_ANALYZER_SEOSOYOUNG_LOGS")


def get_soulstream_logs() -> Path:
    return _env_path("LOG_ANALYZER_SOULSTREAM_LOGS")


def get_sessions_dir() -> Path:
    return _env_path("LOG_ANALYZER_SESSIONS_DIR")


@dataclass(frozen=True, slots=True)
class LogFile:
    path: Path
    component: str
    runtime: str  # "seosoyoung" | "soulstream"
    size_bytes: int
    last_modified: datetime
    date_hint: date | None  # bot_YYYYMMDD에서 추출


# 파일명 → 컴포넌트 분류 패턴
_COMPONENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^bot_\d{8}\.log$"), "bot"),
    (re.compile(r"^bot-error\.log$"), "bot-error"),
    (re.compile(r"^bot-out\.log$"), "bot-out"),
    (re.compile(r"^watchdog\.log$"), "watchdog"),
    (re.compile(r"^watchdog_startup\.log$"), "watchdog-startup"),
    (re.compile(r"^supervisor\.log$"), "supervisor"),
    (re.compile(r"^mcp-([\w-]+?)-(error|out)\.log$"), "mcp"),
    (re.compile(r"^cli_stderr"), "cli-stderr"),
    (re.compile(r"^rescue"), "rescue"),
    (re.compile(r"^service_std(err|out)"), "service-stdio"),
    (re.compile(r"^soulstream-server-(error|out)\.log$"), "soulstream-server"),
    (re.compile(r"^soulstream-dashboard-(error|out)\.log$"), "soulstream-dashboard"),
    (re.compile(r"^seosoyoung-soul-(error|out)\.log$"), "seosoyoung-soul"),
    (re.compile(r"^soul-dashboard-(error|out)\.log$"), "soul-dashboard"),
    (re.compile(r"^pip_"), "pip"),
]

# bot_YYYYMMDD.log에서 날짜 추출
_DATE_RE = re.compile(r"_(\d{4})(\d{2})(\d{2})\.")


def _classify_component(filename: str) -> str:
    """파일명에서 컴포넌트를 추론한다."""
    for pattern, comp in _COMPONENT_PATTERNS:
        m = pattern.match(filename)
        if m:
            if comp == "mcp":
                return f"mcp-{m.group(1)}"
            if comp in ("soulstream-server", "soulstream-dashboard"):
                suffix = m.group(1)  # "error" or "out"
                if suffix == "error":
                    return f"{comp}-error"
                return comp
            return comp
    return "unknown"


def _extract_date_hint(filename: str) -> date | None:
    """파일명에서 날짜 힌트를 추출한다."""
    m = _DATE_RE.search(filename)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def scan_logs(
    *,
    component: str | None = None,
    runtime: str | None = None,
) -> list[LogFile]:
    """두 런타임의 로그 파일을 스캔하여 LogFile 목록을 반환한다.

    Args:
        component: 특정 컴포넌트만 필터링 (부분 매칭)
        runtime: "seosoyoung" 또는 "soulstream"만 필터링
    """
    results: list[LogFile] = []

    dirs = []
    if runtime is None or runtime == "seosoyoung":
        dirs.append((get_seosoyoung_logs(), "seosoyoung"))
    if runtime is None or runtime == "soulstream":
        dirs.append((get_soulstream_logs(), "soulstream"))

    for log_dir, rt in dirs:
        if not log_dir.exists():
            continue
        for p in log_dir.iterdir():
            if not p.is_file() or p.suffix != ".log":
                continue
            comp = _classify_component(p.name)
            if component and component not in comp:
                continue
            stat = p.stat()
            results.append(
                LogFile(
                    path=p,
                    component=comp,
                    runtime=rt,
                    size_bytes=stat.st_size,
                    last_modified=datetime.fromtimestamp(stat.st_mtime),
                    date_hint=_extract_date_hint(p.name),
                )
            )

    results.sort(key=lambda f: f.last_modified, reverse=True)
    return results
