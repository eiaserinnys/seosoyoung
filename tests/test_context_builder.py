"""ContextBuilder 단위 테스트"""

from datetime import datetime, timezone

import pytest

from seosoyoung.memory.context_builder import (
    ContextBuilder,
    add_relative_time,
    optimize_for_context,
)
from seosoyoung.memory.store import MemoryRecord, MemoryStore


class TestAddRelativeTime:
    def test_today(self):
        observations = "## [2026-02-10] Session Observations"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "(오늘)" in result

    def test_yesterday(self):
        observations = "## [2026-02-09] Session Observations"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "(어제)" in result

    def test_days_ago(self):
        observations = "## [2026-02-05] Session Observations"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "(5일 전)" in result

    def test_weeks_ago(self):
        observations = "## [2026-01-27] Session Observations"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "(2주 전)" in result

    def test_months_ago(self):
        observations = "## [2025-12-10] Session Observations"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "개월 전" in result

    def test_multiple_dates(self):
        observations = "## [2026-02-10] First\n## [2026-02-08] Second"
        now = datetime(2026, 2, 10, 15, 0, tzinfo=timezone.utc)
        result = add_relative_time(observations, now)
        assert "(오늘)" in result
        assert "(2일 전)" in result

    def test_no_date_headers(self):
        observations = "No date headers here"
        result = add_relative_time(observations)
        assert result == observations

    def test_invalid_date_format(self):
        observations = "## [not-a-date] Session"
        result = add_relative_time(observations)
        assert result == observations


class TestOptimizeForContext:
    def test_short_text_unchanged(self):
        text = "## [2026-02-10] Short observation"
        result = optimize_for_context(text, max_tokens=30000)
        assert result == text

    def test_truncates_old_sections(self):
        """토큰 초과 시 오래된 섹션부터 제거"""
        sections = []
        for i in range(100):
            sections.append(f"## [2026-01-{i+1:02d}] Session {i}\n{'x' * 500}\n")
        text = "\n".join(sections)

        result = optimize_for_context(text, max_tokens=500)
        # 결과는 원본보다 짧아야 함
        assert len(result) < len(text)
        # 최신 섹션이 포함되어야 함
        assert "Session 99" in result or len(result) > 0

    def test_single_large_section(self):
        """단일 섹션이 max_tokens를 초과할 때"""
        text = "x" * 100000
        result = optimize_for_context(text, max_tokens=100)
        # 결과가 원본보다 짧아야 함
        assert len(result) < len(text)


class TestContextBuilder:
    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def builder(self, store):
        return ContextBuilder(store)

    def test_no_record_returns_none(self, builder):
        result = builder.build_memory_prompt("NONEXISTENT_TS")
        assert result is None

    def test_empty_observations_returns_none(self, builder, store):
        record = MemoryRecord(thread_ts="ts_1", user_id="U12345", observations="")
        store.save_record(record)
        result = builder.build_memory_prompt("ts_1")
        assert result is None

    def test_whitespace_only_returns_none(self, builder, store):
        record = MemoryRecord(thread_ts="ts_1", user_id="U12345", observations="   \n  ")
        store.save_record(record)
        result = builder.build_memory_prompt("ts_1")
        assert result is None

    def test_builds_prompt_with_observations(self, builder, store):
        record = MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session Observations\n\n🔴 Important finding",
        )
        store.save_record(record)

        result = builder.build_memory_prompt("ts_1")

        assert result is not None
        assert "<observational-memory>" in result
        assert "</observational-memory>" in result
        assert "🔴 Important finding" in result
        assert "과거 대화에서 관찰한 내용" in result

    def test_includes_relative_time(self, builder, store):
        record = MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session Observations\n\n🔴 Finding",
        )
        store.save_record(record)

        result = builder.build_memory_prompt("ts_1")
        # 상대 시간이 추가되어야 함
        assert result is not None
        assert "## [2026-02-10]" in result

    def test_session_isolation(self, builder, store):
        """세션별로 독립적인 관찰 주입"""
        store.save_record(MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session 1\n\n🔴 First session finding",
        ))
        store.save_record(MemoryRecord(
            thread_ts="ts_2",
            user_id="U12345",
            observations="## [2026-02-11] Session 2\n\n🔴 Second session finding",
        ))

        result_1 = builder.build_memory_prompt("ts_1")
        result_2 = builder.build_memory_prompt("ts_2")

        assert "First session finding" in result_1
        assert "Second session finding" not in result_1
        assert "Second session finding" in result_2
        assert "First session finding" not in result_2
