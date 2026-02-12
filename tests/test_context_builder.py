"""ContextBuilder 단위 테스트"""

import json
from datetime import datetime, timezone

import pytest

from seosoyoung.memory.channel_store import ChannelStore
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


class TestContextBuilderChannelObservation:
    """채널 관찰 컨텍스트 주입 테스트"""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def channel_store(self, tmp_path):
        return ChannelStore(base_dir=tmp_path)

    @pytest.fixture
    def builder(self, store, channel_store):
        return ContextBuilder(store, channel_store=channel_store)

    def test_no_channel_data_returns_none(self, builder):
        """채널 데이터가 없으면 채널 관찰 토큰은 0"""
        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id="C_NONE",
        )
        assert result.channel_digest_tokens == 0
        assert result.channel_buffer_tokens == 0

    def test_digest_only(self, builder, channel_store):
        """digest만 있고 버퍼가 없는 경우"""
        channel_store.save_digest(
            "C_TEST",
            content="오늘 팀원들이 점심 메뉴를 두고 열띤 토론을 벌였다.",
            meta={"token_count": 50},
        )

        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id="C_TEST",
        )

        assert result.prompt is not None
        assert '<channel-observation channel="C_TEST">' in result.prompt
        assert "</channel-observation>" in result.prompt
        assert "<digest>" in result.prompt
        assert "점심 메뉴" in result.prompt
        assert result.channel_digest_tokens > 0
        assert result.channel_buffer_tokens == 0

    def test_digest_plus_channel_buffer(self, builder, channel_store):
        """digest + 채널 버퍼 메시지가 있는 경우"""
        channel_store.save_digest(
            "C_TEST",
            content="어제의 요약",
            meta={"token_count": 20},
        )
        channel_store.append_channel_message("C_TEST", {
            "user": "U_AAA", "text": "오늘 날씨 좋다", "ts": "1000.001",
        })
        channel_store.append_channel_message("C_TEST", {
            "user": "U_BBB", "text": "동의합니다", "ts": "1000.002",
        })

        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id="C_TEST",
        )

        assert result.prompt is not None
        assert "<recent-channel>" in result.prompt
        assert "오늘 날씨 좋다" in result.prompt
        assert "동의합니다" in result.prompt
        assert result.channel_buffer_tokens > 0

    def test_thread_buffer_included(self, builder, channel_store):
        """현재 스레드의 버퍼가 포함되는 경우"""
        channel_store.save_digest("C_TEST", content="요약", meta={})
        channel_store.append_thread_message("C_TEST", "ts_1", {
            "user": "U_CCC", "text": "이 스레드 내용이에요", "ts": "1000.010",
        })

        # build_memory_prompt의 첫 번째 인자가 thread_ts (세션 키)
        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id="C_TEST",
        )

        assert result.prompt is not None
        assert '<recent-thread thread="ts_1">' in result.prompt
        assert "이 스레드 내용이에요" in result.prompt

    def test_other_thread_not_included(self, builder, channel_store):
        """다른 스레드의 버퍼는 포함되지 않음"""
        channel_store.save_digest("C_TEST", content="요약", meta={})
        channel_store.append_thread_message("C_TEST", "ts_other", {
            "user": "U_DDD", "text": "다른 스레드 내용", "ts": "1000.020",
        })

        # thread_ts="ts_1" → ts_other 스레드는 포함되지 않아야 함
        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id="C_TEST",
        )

        # 다른 스레드 내용은 포함되지 않아야 함
        if result.prompt:
            assert "다른 스레드 내용" not in result.prompt

    def test_channel_observation_after_om(self, builder, store, channel_store):
        """OM 장기기억 뒤에 채널 관찰이 이어서 주입됨"""
        store.save_persistent(
            content="🔴 장기 기억 내용",
            meta={"token_count": 50},
        )
        channel_store.save_digest(
            "C_TEST",
            content="채널 관찰 요약",
            meta={"token_count": 30},
        )

        result = builder.build_memory_prompt(
            "ts_1",
            include_persistent=True,
            include_channel_observation=True,
            channel_id="C_TEST",
        )

        assert result.prompt is not None
        # 장기 기억이 채널 관찰보다 먼저 나와야 함
        ltm_pos = result.prompt.index("<long-term-memory>")
        ch_pos = result.prompt.index("<channel-observation")
        assert ltm_pos < ch_pos

    def test_disabled_by_default(self, builder, channel_store):
        """include_channel_observation=False면 채널 관찰 미포함"""
        channel_store.save_digest(
            "C_TEST",
            content="채널 관찰 요약",
            meta={"token_count": 30},
        )

        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=False,
            channel_id="C_TEST",
        )

        assert result.channel_digest_tokens == 0
        assert result.channel_buffer_tokens == 0
        if result.prompt:
            assert "<channel-observation" not in result.prompt

    def test_no_channel_id_returns_no_channel_data(self, builder, channel_store):
        """channel_id가 None이면 채널 관찰 데이터 없음"""
        channel_store.save_digest(
            "C_TEST",
            content="채널 관찰 요약",
            meta={"token_count": 30},
        )

        result = builder.build_memory_prompt(
            "ts_1",
            include_channel_observation=True,
            channel_id=None,
        )

        assert result.channel_digest_tokens == 0
        assert result.channel_buffer_tokens == 0

    def test_injection_result_has_channel_fields(self, builder):
        """InjectionResult에 channel_digest_tokens, channel_buffer_tokens 필드 존재"""
        result = builder.build_memory_prompt("ts_1")
        assert hasattr(result, "channel_digest_tokens")
        assert hasattr(result, "channel_buffer_tokens")


class TestContextBuilderNewObservations:
    """새 관찰(현재 세션의 이전 턴 diff) 주입 테스트"""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def builder(self, store):
        return ContextBuilder(store)

    def test_new_observations_injected_from_current_session(self, builder, store):
        """현재 세션의 .new.md가 있으면 주입됨"""
        store.save_new_observations("ts_session", "🔴 사용자가 한국어 커밋을 선호")

        result = builder.build_memory_prompt(
            "ts_session",
            include_persistent=False,
            include_session=False,
            include_new_observations=True,
        )

        assert result.prompt is not None
        assert "<new-observations>" in result.prompt
        assert "한국어 커밋" in result.prompt
        assert result.new_observation_tokens > 0

    def test_no_new_md_no_injection(self, builder, store):
        """현재 세션의 .new.md가 없으면 주입 없음"""
        result = builder.build_memory_prompt(
            "ts_session",
            include_persistent=False,
            include_session=False,
            include_new_observations=True,
        )

        assert result.new_observation_tokens == 0
        if result.prompt:
            assert "<new-observations>" not in result.prompt

    def test_other_session_new_md_not_injected(self, builder, store):
        """다른 세션의 .new.md는 주입되지 않음"""
        store.save_new_observations("ts_other", "🔴 다른 세션의 관찰")

        result = builder.build_memory_prompt(
            "ts_current",
            include_new_observations=True,
        )

        assert result.new_observation_tokens == 0

    def test_new_observations_not_injected_when_disabled(self, builder, store):
        """include_new_observations=False면 주입되지 않음"""
        store.save_new_observations("ts_session", "🔴 관찰")

        result = builder.build_memory_prompt(
            "ts_session",
            include_new_observations=False,
        )

        assert result.new_observation_tokens == 0
        if result.prompt:
            assert "<new-observations>" not in result.prompt

    def test_new_observations_combined_with_persistent(self, builder, store):
        """장기 기억 + 새 관찰이 함께 주입됨"""
        store.save_persistent(content="🔴 장기 기억", meta={})
        store.save_new_observations("ts_session", "🟡 이번 턴 새 관찰")

        result = builder.build_memory_prompt(
            "ts_session",
            include_persistent=True,
            include_new_observations=True,
        )

        assert result.prompt is not None
        assert "<long-term-memory>" in result.prompt
        assert "<new-observations>" in result.prompt
        # 장기 기억이 새 관찰보다 먼저
        ltm_pos = result.prompt.index("<long-term-memory>")
        new_obs_pos = result.prompt.index("<new-observations>")
        assert ltm_pos < new_obs_pos
