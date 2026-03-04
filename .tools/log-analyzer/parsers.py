"""로그 형식 파서 — watchdog / supervisor / bot / soulstream / fallback"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime | None
    level: str  # DEBUG / INFO / WARNING / ERROR / CRITICAL / UNKNOWN
    message: str
    raw: str
    component: str
    line_number: int


class LogParser(Protocol):
    """모든 파서가 따르는 인터페이스."""

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        """한 줄을 파싱해서 LogEntry를 반환한다. 파싱 불가 시 None."""
        ...


# Watchdog: [2026-02-13 11:07:33] [watchdog] message
_WATCHDOG_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[watchdog\] (.*)"
)


class WatchdogParser:
    __slots__ = ()

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        m = _WATCHDOG_RE.match(line)
        if not m:
            return None
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return LogEntry(
            timestamp=ts,
            level="INFO",
            message=m.group(2),
            raw=line,
            component=component,
            line_number=line_number,
        )


# Supervisor: [2026-02-13 09:59:49] supervisor: [INFO] message
_SUPERVISOR_RE = re.compile(
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] supervisor: \[(\w+)\] (.*)"
)


class SupervisorParser:
    __slots__ = ()

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        m = _SUPERVISOR_RE.match(line)
        if not m:
            return None
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return LogEntry(
            timestamp=ts,
            level=m.group(2).upper(),
            message=m.group(3),
            raw=line,
            component=component,
            line_number=line_number,
        )


# Bot: 2026-03-04 07:06:31,713 [DEBUG] message
_BOT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} \[(\w+)\] (.*)"
)


class BotParser:
    __slots__ = ()

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        m = _BOT_RE.match(line)
        if not m:
            return None
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return LogEntry(
            timestamp=ts,
            level=m.group(2).upper(),
            message=m.group(3),
            raw=line,
            component=component,
            line_number=line_number,
        )


# Soulstream: 2026-03-01 01:38:48 - soulstream - INFO - message
_SOULSTREAM_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - ([\w.]+) - (\w+) - (.*)"
)


class SoulstreamParser:
    __slots__ = ()

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        m = _SOULSTREAM_RE.match(line)
        if not m:
            return None
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return LogEntry(
            timestamp=ts,
            level=m.group(3).upper(),
            message=m.group(4),
            raw=line,
            component=component,
            line_number=line_number,
        )


# Fallback: ISO날짜 추출 시도, 실패하면 timestamp=None (멀티라인 연속)
_ISO_PREFIX_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


class FallbackParser:
    __slots__ = ()

    def parse(self, line: str, component: str, line_number: int) -> LogEntry | None:
        m = _ISO_PREFIX_RE.match(line)
        ts = None
        if m:
            try:
                ts = datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return LogEntry(
            timestamp=ts,
            level="UNKNOWN",
            message=line,
            raw=line,
            component=component,
            line_number=line_number,
        )


# 컴포넌트명 → 파서 매핑
_PARSER_MAP: dict[str, LogParser] = {
    "watchdog": WatchdogParser(),
    "supervisor": SupervisorParser(),
    "bot": BotParser(),
    "bot-error": BotParser(),
    "bot-out": BotParser(),
    "soulstream-server": SoulstreamParser(),
    "soulstream-server-error": SoulstreamParser(),
    "soulstream-dashboard": SoulstreamParser(),
    "soulstream-dashboard-error": SoulstreamParser(),
}

_FALLBACK = FallbackParser()


def get_parser(component: str) -> LogParser:
    """컴포넌트에 맞는 파서를 반환한다. 매핑이 없으면 FallbackParser."""
    return _PARSER_MAP.get(component, _FALLBACK)
