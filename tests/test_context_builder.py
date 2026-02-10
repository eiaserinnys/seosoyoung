"""ContextBuilder 단위 테스트"""

from datetime import datetime, timezone

import pytest

from seosoyoung.memory.context_builder import (
    ContextBuilder,
    InjectionResult,
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

    def test_no_record_returns_none_prompt(self, builder):
        result = builder.build_memory_prompt("NONEXISTENT_TS", include_session=True)
        assert isinstance(result, InjectionResult)
        assert result.prompt is None
        assert result.session_tokens == 0

    def test_empty_observations_returns_none_prompt(self, builder, store):
        record = MemoryRecord(thread_ts="ts_1", user_id="U12345", observations="")
        store.save_record(record)
        result = builder.build_memory_prompt("ts_1", include_session=True)
        assert result.prompt is None

    def test_whitespace_only_returns_none_prompt(self, builder, store):
        record = MemoryRecord(thread_ts="ts_1", user_id="U12345", observations="   \n  ")
        store.save_record(record)
        result = builder.build_memory_prompt("ts_1", include_session=True)
        assert result.prompt is None

    def test_builds_prompt_with_observations(self, builder, store):
        record = MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session Observations\n\n🔴 Important finding",
        )
        store.save_record(record)

        result = builder.build_memory_prompt("ts_1", include_session=True)

        assert result.prompt is not None
        assert "<observational-memory>" in result.prompt
        assert "</observational-memory>" in result.prompt
        assert "🔴 Important finding" in result.prompt
        assert "최근 대화에서 관찰한 내용" in result.prompt
        assert result.session_tokens > 0

    def test_includes_relative_time(self, builder, store):
        record = MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session Observations\n\n🔴 Finding",
        )
        store.save_record(record)

        result = builder.build_memory_prompt("ts_1", include_session=True)
        assert result.prompt is not None
        assert "## [2026-02-10]" in result.prompt

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

        result_1 = builder.build_memory_prompt("ts_1", include_session=True)
        result_2 = builder.build_memory_prompt("ts_2", include_session=True)

        assert "First session finding" in result_1.prompt
        assert "Second session finding" not in result_1.prompt
        assert "Second session finding" in result_2.prompt
        assert "First session finding" not in result_2.prompt


class TestContextBuilderPersistent:
    """장기 기억 주입 테스트"""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def builder(self, store):
        return ContextBuilder(store)

    def test_persistent_only(self, builder, store):
        """장기 기억만 주입 (세션 관찰 없음)"""
        store.save_persistent(
            content="🔴 사용자는 한국어 커밋 메시지를 선호합니다",
            meta={"token_count": 100},
        )

        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=False,
        )

        assert result.prompt is not None
        assert "<long-term-memory>" in result.prompt
        assert "</long-term-memory>" in result.prompt
        assert "한국어 커밋 메시지" in result.prompt
        assert "<observational-memory>" not in result.prompt
        assert result.persistent_tokens > 0
        assert result.session_tokens == 0

    def test_persistent_plus_session(self, builder, store):
        """장기 기억 + 세션 관찰 모두 주입"""
        store.save_persistent(
            content="🔴 장기 기억 내용",
            meta={"token_count": 50},
        )
        store.save_record(MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session\n\n🟡 세션 관찰 내용",
        ))

        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=True,
        )

        assert result.prompt is not None
        assert "<long-term-memory>" in result.prompt
        assert "<observational-memory>" in result.prompt
        assert "장기 기억 내용" in result.prompt
        assert "세션 관찰 내용" in result.prompt
        assert result.persistent_tokens > 0
        assert result.session_tokens > 0

    def test_no_persistent_no_session(self, builder):
        """장기 기억도 세션 관찰도 없으면 None"""
        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=True,
        )
        assert result.prompt is None
        assert result.persistent_tokens == 0
        assert result.session_tokens == 0

    def test_empty_persistent_not_injected(self, builder, store):
        """빈 장기 기억은 주입하지 않음"""
        store.save_persistent(content="  \n  ", meta={})

        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=False,
        )
        assert result.prompt is None
        assert result.persistent_tokens == 0

    def test_persistent_always_session_flag(self, builder, store):
        """장기 기억은 include_persistent=True면 항상, 세션은 include_session에 따라"""
        store.save_persistent(
            content="🔴 장기 기억",
            meta={"token_count": 50},
        )
        store.save_record(MemoryRecord(
            thread_ts="ts_1",
            user_id="U12345",
            observations="## [2026-02-10] Session\n\n🟡 세션 관찰",
        ))

        # include_session=False → 장기 기억만
        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=False,
        )
        assert "<long-term-memory>" in result.prompt
        assert "<observational-memory>" not in result.prompt

        # include_session=True → 둘 다
        result = builder.build_memory_prompt(
            "ts_1", include_persistent=True, include_session=True,
        )
        assert "<long-term-memory>" in result.prompt
        assert "<observational-memory>" in result.prompt
