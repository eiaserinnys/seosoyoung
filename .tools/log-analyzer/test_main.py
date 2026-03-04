"""로그 분석 도구 유닛 테스트 + 통합 테스트."""

from __future__ import annotations

import sys
import tempfile
import textwrap
from datetime import datetime, date
from pathlib import Path
from unittest import TestCase, main

# 도구 디렉토리를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from parsers import (
    BotParser,
    FallbackParser,
    LogEntry,
    SoulstreamParser,
    SupervisorParser,
    WatchdogParser,
    get_parser,
)
from scanner import LogFile, _classify_component, _extract_date_hint
from searcher import search_file, _level_set
from segments import find_segments, SessionSegment
from formatter import format_locate, format_entries, format_segments, _human_size


class TestWatchdogParser(TestCase):
    def setUp(self):
        self.parser = WatchdogParser()

    def test_parse_valid(self):
        line = "[2026-02-13 11:07:33] [watchdog] supervisor 감시 시작"
        entry = self.parser.parse(line, "watchdog", 1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 2, 13, 11, 7, 33))
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.message, "supervisor 감시 시작")
        self.assertEqual(entry.component, "watchdog")
        self.assertEqual(entry.line_number, 1)

    def test_parse_invalid(self):
        entry = self.parser.parse("not a watchdog line", "watchdog", 1)
        self.assertIsNone(entry)


class TestSupervisorParser(TestCase):
    def setUp(self):
        self.parser = SupervisorParser()

    def test_parse_valid(self):
        line = "[2026-02-13 09:59:49] supervisor: [INFO] bot: 시작됨 (pid=61768)"
        entry = self.parser.parse(line, "supervisor", 5)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 2, 13, 9, 59, 49))
        self.assertEqual(entry.level, "INFO")
        self.assertIn("bot: 시작됨", entry.message)

    def test_parse_error_level(self):
        line = "[2026-02-13 10:00:00] supervisor: [ERROR] 프로세스 crash"
        entry = self.parser.parse(line, "supervisor", 10)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, "ERROR")


class TestBotParser(TestCase):
    def setUp(self):
        self.parser = BotParser()

    def test_parse_valid(self):
        line = "2026-03-04 07:06:32,143 [INFO] SeoSoyoung 봇을 시작합니다..."
        entry = self.parser.parse(line, "bot", 3)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 3, 4, 7, 6, 32))
        self.assertEqual(entry.level, "INFO")
        self.assertIn("SeoSoyoung 봇을 시작합니다", entry.message)

    def test_parse_debug(self):
        line = "2026-03-04 07:06:31,713 [DEBUG] Sending a request - url: https://slack.com/api/auth.test"
        entry = self.parser.parse(line, "bot", 1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, "DEBUG")


class TestSoulstreamParser(TestCase):
    def setUp(self):
        self.parser = SoulstreamParser()

    def test_parse_valid(self):
        line = "2026-03-01 01:38:48 - soulstream - INFO - Soulstream starting..."
        entry = self.parser.parse(line, "soulstream-server", 1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 3, 1, 1, 38, 48))
        self.assertEqual(entry.level, "INFO")
        self.assertEqual(entry.message, "Soulstream starting...")


class TestFallbackParser(TestCase):
    def setUp(self):
        self.parser = FallbackParser()

    def test_parse_with_iso_prefix(self):
        line = "2026-03-01 12:00:00 some unstructured log"
        entry = self.parser.parse(line, "unknown", 1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 3, 1, 12, 0, 0))
        self.assertEqual(entry.level, "UNKNOWN")

    def test_parse_without_timestamp(self):
        line = "    at Function.run (/app/node_modules/.bin/start.js:10:5)"
        entry = self.parser.parse(line, "unknown", 2)
        self.assertIsNotNone(entry)
        self.assertIsNone(entry.timestamp)

    def test_parse_with_iso_t_separator(self):
        line = "2026-03-01T12:00:00 something happened"
        entry = self.parser.parse(line, "unknown", 1)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.timestamp, datetime(2026, 3, 1, 12, 0, 0))


class TestGetParser(TestCase):
    def test_known_components(self):
        self.assertIsInstance(get_parser("watchdog"), WatchdogParser)
        self.assertIsInstance(get_parser("supervisor"), SupervisorParser)
        self.assertIsInstance(get_parser("bot"), BotParser)
        self.assertIsInstance(get_parser("bot-error"), BotParser)
        self.assertIsInstance(get_parser("soulstream-server"), SoulstreamParser)

    def test_unknown_component(self):
        self.assertIsInstance(get_parser("anything-else"), FallbackParser)


class TestClassifyComponent(TestCase):
    def test_bot_daily(self):
        self.assertEqual(_classify_component("bot_20260304.log"), "bot")

    def test_bot_error(self):
        self.assertEqual(_classify_component("bot-error.log"), "bot-error")

    def test_watchdog(self):
        self.assertEqual(_classify_component("watchdog.log"), "watchdog")

    def test_supervisor(self):
        self.assertEqual(_classify_component("supervisor.log"), "supervisor")

    def test_mcp(self):
        self.assertEqual(_classify_component("mcp-slack-error.log"), "mcp-slack")
        self.assertEqual(_classify_component("mcp-trello-out.log"), "mcp-trello")
        self.assertEqual(_classify_component("mcp-seosoyoung-error.log"), "mcp-seosoyoung")

    def test_cli_stderr(self):
        self.assertEqual(_classify_component("cli_stderr.log"), "cli-stderr")
        self.assertEqual(_classify_component("cli_stderr_1771854569_779209.log"), "cli-stderr")

    def test_soulstream(self):
        self.assertEqual(_classify_component("soulstream-server-out.log"), "soulstream-server")
        self.assertEqual(_classify_component("soulstream-server-error.log"), "soulstream-server-error")
        self.assertEqual(_classify_component("soulstream-dashboard-out.log"), "soulstream-dashboard")

    def test_unknown(self):
        self.assertEqual(_classify_component("random.log"), "unknown")


class TestExtractDateHint(TestCase):
    def test_bot_daily(self):
        self.assertEqual(_extract_date_hint("bot_20260304.log"), date(2026, 3, 4))

    def test_no_date(self):
        self.assertIsNone(_extract_date_hint("watchdog.log"))


class TestLevelSet(TestCase):
    def test_error_level(self):
        result = _level_set("ERROR")
        self.assertEqual(result, {"ERROR", "CRITICAL"})

    def test_debug_level(self):
        result = _level_set("DEBUG")
        self.assertEqual(result, {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

    def test_unknown_level(self):
        result = _level_set("CUSTOM")
        self.assertEqual(result, {"CUSTOM"})


class TestSearchFile(TestCase):
    def test_search_with_level_filter(self):
        content = textwrap.dedent("""\
            2026-03-04 10:00:00,000 [DEBUG] debug message
            2026-03-04 10:00:01,000 [INFO] info message
            2026-03-04 10:00:02,000 [ERROR] error message
            2026-03-04 10:00:03,000 [CRITICAL] critical message
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            entries = search_file(path, "bot", level="ERROR")
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0].level, "ERROR")
            self.assertEqual(entries[1].level, "CRITICAL")
        finally:
            path.unlink()

    def test_search_with_time_range(self):
        content = textwrap.dedent("""\
            2026-03-04 10:00:00,000 [INFO] too early
            2026-03-04 11:00:00,000 [INFO] in range
            2026-03-04 12:00:00,000 [INFO] also in range
            2026-03-04 13:00:00,000 [INFO] too late
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            entries = search_file(
                path,
                "bot",
                start_time=datetime(2026, 3, 4, 10, 30),
                end_time=datetime(2026, 3, 4, 12, 30),
            )
            self.assertEqual(len(entries), 2)
            self.assertIn("in range", entries[0].message)
        finally:
            path.unlink()

    def test_search_with_tail(self):
        content = "\n".join(
            f"2026-03-04 10:{i:02d}:00,000 [INFO] message {i}" for i in range(20)
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            entries = search_file(path, "bot", tail=5)
            self.assertEqual(len(entries), 5)
            self.assertIn("message 19", entries[-1].message)
        finally:
            path.unlink()

    def test_search_with_pattern(self):
        import re

        content = textwrap.dedent("""\
            2026-03-04 10:00:00,000 [INFO] start server
            2026-03-04 10:00:01,000 [ERROR] connection failed
            2026-03-04 10:00:02,000 [INFO] retry connection
            2026-03-04 10:00:03,000 [ERROR] timeout error
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            entries = search_file(path, "bot", pattern=re.compile(r"connection"))
            self.assertEqual(len(entries), 2)
        finally:
            path.unlink()


class TestFindSegments(TestCase):
    def test_watchdog_segments(self):
        content = textwrap.dedent("""\
            [2026-03-04 10:00:00] [watchdog] supervisor 감시 시작
            [2026-03-04 10:00:01] [watchdog] supervisor 시작
            [2026-03-04 10:05:00] [watchdog] supervisor 종료: exit=0, uptime=300s
            [2026-03-04 10:05:00] [watchdog] 정상 종료, 루프 탈출
            [2026-03-04 11:00:00] [watchdog] supervisor 감시 시작
            [2026-03-04 11:00:01] [watchdog] supervisor 시작
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            segments = find_segments(path, "watchdog")
            self.assertGreaterEqual(len(segments), 2)

            # 첫 세그먼트는 종료된 상태
            first = segments[0]
            self.assertEqual(first.start_time, datetime(2026, 3, 4, 10, 0, 0))
            self.assertIsNotNone(first.end_time)

            # 마지막 세그먼트는 열린 상태 (종료 마커 없음)
            last = segments[-1]
            self.assertIsNone(last.end_marker)
        finally:
            path.unlink()

    def test_segments_with_last(self):
        content = textwrap.dedent("""\
            [2026-03-04 10:00:00] [watchdog] supervisor 감시 시작
            [2026-03-04 10:05:00] [watchdog] 정상 종료, 루프 탈출
            [2026-03-04 11:00:00] [watchdog] supervisor 감시 시작
            [2026-03-04 11:05:00] [watchdog] 정상 종료, 루프 탈출
            [2026-03-04 12:00:00] [watchdog] supervisor 감시 시작
            [2026-03-04 12:05:00] [watchdog] 정상 종료, 루프 탈출
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            segments = find_segments(path, "watchdog", last=2)
            self.assertEqual(len(segments), 2)
            self.assertEqual(segments[0].start_time, datetime(2026, 3, 4, 11, 0, 0))
        finally:
            path.unlink()


class TestFormatter(TestCase):
    def test_human_size(self):
        self.assertEqual(_human_size(500), "500 B")
        self.assertEqual(_human_size(1500), "1.5 KB")
        self.assertEqual(_human_size(1500000), "1.4 MB")
        self.assertEqual(_human_size(1500000000), "1.4 GB")

    def test_format_locate_empty(self):
        self.assertIn("찾지 못했습니다", format_locate([]))

    def test_format_entries_empty(self):
        self.assertIn("없습니다", format_entries([]))

    def test_format_segments_empty(self):
        self.assertIn("찾지 못했습니다", format_segments([]))

    def test_format_locate_with_files(self):
        files = [
            LogFile(
                path=Path("D:/soyoung_root/seosoyoung_runtime/logs/bot_20260304.log"),
                component="bot",
                runtime="seosoyoung",
                size_bytes=1024000,
                last_modified=datetime(2026, 3, 4, 12, 0, 0),
                date_hint=date(2026, 3, 4),
            )
        ]
        output = format_locate(files)
        self.assertIn("bot_20260304.log", output)
        self.assertIn("1000.0 KB", output)
        self.assertIn("총 1개 파일", output)

    def test_format_entries_with_data(self):
        entries = [
            LogEntry(
                timestamp=datetime(2026, 3, 4, 12, 0, 0),
                level="ERROR",
                message="something failed",
                raw="raw line",
                component="bot",
                line_number=42,
            )
        ]
        output = format_entries(entries)
        self.assertIn("ERROR", output)
        self.assertIn("something failed", output)
        self.assertIn("총 1건", output)

    def test_format_segments_with_data(self):
        segments = [
            SessionSegment(
                start_time=datetime(2026, 3, 4, 10, 0, 0),
                end_time=datetime(2026, 3, 4, 10, 30, 0),
                start_marker="supervisor 감시 시작",
                end_marker="정상 종료",
                exit_code=0,
                component="watchdog",
            )
        ]
        output = format_segments(segments)
        self.assertIn("10:00:00", output)
        self.assertIn("30m", output)
        self.assertIn("총 1개 세션", output)


if __name__ == "__main__":
    main()
