"""채널 개입(intervention) 단위 테스트

InterventionHistory + intervention_probability + 마크업 파서 + 슬랙 발송 테스트
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.channel_intervention import (
    InterventionAction,
    InterventionHistory,
    intervention_probability,
    parse_intervention_markup,
    execute_interventions,
    send_collect_debug_log,
    send_debug_log,
    send_digest_skip_debug_log,
    send_intervention_probability_debug_log,
)
from seosoyoung.memory.channel_observer import (
    ChannelObserverResult,
    DigestResult,
    JudgeResult,
)
from seosoyoung.memory.channel_pipeline import run_channel_pipeline
from seosoyoung.memory.channel_store import ChannelStore


# ── parse_intervention_markup ────────────────────────────

class TestParseInterventionMarkup:
    """ChannelObserverResult를 InterventionAction 리스트로 변환"""

    def test_none_reaction_returns_empty(self):
        result = ChannelObserverResult(
            digest="test",
            importance=2,
            reaction_type="none",
        )
        actions = parse_intervention_markup(result)
        assert actions == []

    def test_react_action(self):
        result = ChannelObserverResult(
            digest="test",
            importance=5,
            reaction_type="react",
            reaction_target="1234567890.123",
            reaction_content="laughing",
        )
        actions = parse_intervention_markup(result)
        assert len(actions) == 1
        assert actions[0].type == "react"
        assert actions[0].target == "1234567890.123"
        assert actions[0].content == "laughing"

    def test_intervene_channel(self):
        result = ChannelObserverResult(
            digest="test",
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="아이고, 무슨 일이오?",
        )
        actions = parse_intervention_markup(result)
        assert len(actions) == 1
        assert actions[0].type == "message"
        assert actions[0].target == "channel"
        assert actions[0].content == "아이고, 무슨 일이오?"

    def test_intervene_thread(self):
        result = ChannelObserverResult(
            digest="test",
            importance=7,
            reaction_type="intervene",
            reaction_target="thread:1234567890.123",
            reaction_content="그 이야기 자세히 해주시겠소?",
        )
        actions = parse_intervention_markup(result)
        assert len(actions) == 1
        assert actions[0].type == "message"
        assert actions[0].target == "1234567890.123"
        assert actions[0].content == "그 이야기 자세히 해주시겠소?"

    def test_missing_content_returns_empty(self):
        """content가 없는 react/intervene은 건너뜀"""
        result = ChannelObserverResult(
            digest="test",
            importance=5,
            reaction_type="react",
            reaction_target="1234.5678",
            reaction_content=None,
        )
        actions = parse_intervention_markup(result)
        assert actions == []

    def test_missing_target_returns_empty(self):
        result = ChannelObserverResult(
            digest="test",
            importance=5,
            reaction_type="intervene",
            reaction_target=None,
            reaction_content="메시지",
        )
        actions = parse_intervention_markup(result)
        assert actions == []


# ── execute_interventions ────────────────────────────────

class TestExecuteInterventions:
    """슬랙 API 발송 로직 테스트"""

    @pytest.mark.asyncio
    async def test_send_channel_message(self):
        """target=channel → chat_postMessage(channel=ch)"""
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        actions = [InterventionAction(type="message", target="channel", content="안녕")]
        results = await execute_interventions(client, "C123", actions)

        client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="안녕",
        )
        assert len(results) == 1
        assert results[0]["ok"] is True

    @pytest.mark.asyncio
    async def test_send_thread_message(self):
        """target=thread_ts → chat_postMessage(channel=ch, thread_ts=ts)"""
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        actions = [
            InterventionAction(type="message", target="1234.5678", content="답글")
        ]
        results = await execute_interventions(client, "C123", actions)

        client.chat_postMessage.assert_called_once_with(
            channel="C123",
            text="답글",
            thread_ts="1234.5678",
        )

    @pytest.mark.asyncio
    async def test_send_reaction(self):
        """type=react → reactions_add"""
        client = MagicMock()
        client.reactions_add = MagicMock(return_value={"ok": True})

        actions = [
            InterventionAction(type="react", target="1234.5678", content="laughing")
        ]
        results = await execute_interventions(client, "C123", actions)

        client.reactions_add.assert_called_once_with(
            channel="C123",
            timestamp="1234.5678",
            name="laughing",
        )

    @pytest.mark.asyncio
    async def test_api_error_is_caught(self):
        """API 호출 실패 시 에러가 잡히고 나머지 액션은 계속 실행"""
        client = MagicMock()
        client.reactions_add = MagicMock(side_effect=Exception("API error"))
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        actions = [
            InterventionAction(type="react", target="1.1", content="smile"),
            InterventionAction(type="message", target="channel", content="메시지"),
        ]
        results = await execute_interventions(client, "C123", actions)

        # 첫 번째 실패, 두 번째 성공
        assert len(results) == 2
        assert results[0] is None  # 실패한 것
        assert results[1]["ok"] is True

    @pytest.mark.asyncio
    async def test_empty_actions(self):
        """빈 액션 리스트는 아무것도 하지 않음"""
        client = MagicMock()
        results = await execute_interventions(client, "C123", [])
        assert results == []


# ── intervention_probability ─────────────────────────────

class TestInterventionProbability:
    """확률 함수 단위 테스트"""

    def test_zero_minutes_returns_near_zero(self):
        """경과 시간 0분이면 확률이 거의 0"""
        # jitter 범위를 고려해서 여러 번 실행하여 평균 확인
        values = [intervention_probability(0.0, 0) for _ in range(100)]
        avg = sum(values) / len(values)
        assert avg < 0.05

    def test_long_time_returns_near_one(self):
        """경과 시간이 충분히 길면 확률이 1에 가까움"""
        values = [intervention_probability(300.0, 0) for _ in range(100)]
        avg = sum(values) / len(values)
        assert avg > 0.9

    def test_recent_count_suppresses(self):
        """최근 개입 횟수가 많으면 확률이 낮아짐"""
        values_0 = [intervention_probability(60.0, 0) for _ in range(100)]
        values_5 = [intervention_probability(60.0, 5) for _ in range(100)]
        avg_0 = sum(values_0) / len(values_0)
        avg_5 = sum(values_5) / len(values_5)
        assert avg_5 < avg_0

    def test_result_capped_at_one(self):
        """결과는 최대 1.0"""
        for _ in range(100):
            p = intervention_probability(10000.0, 0)
            assert p <= 1.0

    def test_result_non_negative(self):
        """결과는 0 이상"""
        for _ in range(100):
            p = intervention_probability(0.0, 10)
            assert p >= 0.0

    def test_monotonic_time_increase(self):
        """시간이 길수록 확률 증가 (통계적)"""
        avg_10 = sum(intervention_probability(10, 0) for _ in range(200)) / 200
        avg_60 = sum(intervention_probability(60, 0) for _ in range(200)) / 200
        avg_120 = sum(intervention_probability(120, 0) for _ in range(200)) / 200
        assert avg_10 < avg_60 < avg_120


# ── InterventionHistory ──────────────────────────────────

class TestInterventionHistory:
    """개입 이력 관리 테스트"""

    def test_minutes_since_last_no_history(self, tmp_path):
        """이력 없으면 무한대 반환"""
        h = InterventionHistory(base_dir=tmp_path)
        assert h.minutes_since_last("C123") == float("inf")

    def test_record_and_minutes_since(self, tmp_path):
        """기록 후 경과 시간이 0에 가까움"""
        h = InterventionHistory(base_dir=tmp_path)
        h.record("C123")
        mins = h.minutes_since_last("C123")
        assert mins < 1.0  # 방금 기록했으므로 1분 미만

    def test_recent_count_empty(self, tmp_path):
        """이력 없으면 0"""
        h = InterventionHistory(base_dir=tmp_path)
        assert h.recent_count("C123") == 0

    def test_recent_count_after_records(self, tmp_path):
        """기록 후 카운트 증가"""
        h = InterventionHistory(base_dir=tmp_path)
        h.record("C123")
        h.record("C123")
        h.record("C123")
        assert h.recent_count("C123") == 3

    def test_recent_count_window(self, tmp_path):
        """윈도우 밖의 기록은 카운트에서 제외"""
        h = InterventionHistory(base_dir=tmp_path)
        # 3시간 전 기록 직접 삽입
        meta = h._read_meta("C123")
        meta["history"].append({"at": time.time() - 3 * 3600, "type": "message"})
        h._write_meta("C123", meta)

        assert h.recent_count("C123", window_minutes=120) == 0
        assert h.recent_count("C123", window_minutes=300) == 1

    def test_react_always_allowed(self, tmp_path):
        """이모지 리액션은 항상 허용"""
        h = InterventionHistory(base_dir=tmp_path)
        assert h.can_react("C123") is True

    def test_filter_actions_passes_all(self, tmp_path):
        """filter_actions는 react와 message 모두 통과"""
        h = InterventionHistory(base_dir=tmp_path)
        actions = [
            InterventionAction(type="message", target="channel", content="개입"),
            InterventionAction(type="react", target="1.1", content="smile"),
        ]
        filtered = h.filter_actions("C123", actions)
        assert len(filtered) == 2

    def test_different_channels_independent(self, tmp_path):
        """채널마다 독립적인 이력"""
        h = InterventionHistory(base_dir=tmp_path)
        h.record("C123")
        h.record("C123")
        h.record("C456")

        assert h.recent_count("C123") == 2
        assert h.recent_count("C456") == 1

    def test_history_persists(self, tmp_path):
        """이력이 파일에 저장되어 새 인스턴스에서도 유지"""
        h1 = InterventionHistory(base_dir=tmp_path)
        h1.record("C123")
        h1.record("C123")

        h2 = InterventionHistory(base_dir=tmp_path)
        assert h2.recent_count("C123") == 2

    def test_prune_old_entries(self, tmp_path):
        """record 시 2시간 초과 항목 자동 정리"""
        h = InterventionHistory(base_dir=tmp_path)
        # 오래된 기록 직접 삽입
        meta = {"history": [
            {"at": time.time() - 3 * 3600, "type": "message"},
            {"at": time.time() - 4 * 3600, "type": "message"},
        ]}
        h._write_meta("C123", meta)

        # 새 기록 추가 시 오래된 것들이 정리됨
        h.record("C123")
        meta = h._read_meta("C123")
        assert len(meta["history"]) == 1

    def test_old_format_compat(self, tmp_path):
        """이전 형식(mode/remaining_turns)의 메타 파일도 처리"""
        h = InterventionHistory(base_dir=tmp_path)
        # 이전 형식 메타 직접 작성
        old_meta = {
            "last_intervention_at": time.time(),
            "mode": "active",
            "remaining_turns": 5,
        }
        h._write_meta("C123", old_meta)

        # history 키가 없으면 빈 history로 초기화
        assert h.recent_count("C123") == 0
        assert h.minutes_since_last("C123") == float("inf")


# ── send_debug_log ───────────────────────────────────────

class TestSendDebugLog:
    """디버그 로그 발송 테스트"""

    @pytest.mark.asyncio
    async def test_sends_to_debug_channel_with_blocks(self):
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        result = ChannelObserverResult(
            digest="관찰 내용",
            importance=7,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입 메시지",
        )
        actions_executed = [
            InterventionAction(type="message", target="channel", content="개입 메시지"),
        ]

        await send_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            observer_result=result,
            actions=actions_executed,
            actions_filtered=[],
        )

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_DEBUG"
        # Block Kit blocks 파라미터 존재 확인
        assert "blocks" in call_kwargs
        blocks = call_kwargs["blocks"]
        assert len(blocks) >= 1
        # fallback text도 있어야 함
        assert "text" in call_kwargs
        # 블록 내용에 소스 채널, importance 포함 확인
        blocks_str = json.dumps(blocks, ensure_ascii=False)
        assert "C123" in blocks_str
        assert "7" in blocks_str

    @pytest.mark.asyncio
    async def test_includes_emotion_and_reasoning(self):
        """감정과 판단 이유가 블록에 포함"""
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        result = ChannelObserverResult(
            digest="test", importance=5, reaction_type="none",
        )

        await send_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            observer_result=result,
            actions=[],
            actions_filtered=[],
            reasoning="흥미로운 대화지만 개입할 시점이 아님",
            emotion="관심",
        )

        call_kwargs = client.chat_postMessage.call_args[1]
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "관심" in blocks_str
        assert "흥미로운" in blocks_str

    @pytest.mark.asyncio
    async def test_skips_when_no_debug_channel(self):
        """디버그 채널이 없으면 아무것도 안 함"""
        client = MagicMock()
        result = ChannelObserverResult(digest="test", importance=0, reaction_type="none")

        await send_debug_log(
            client=client,
            debug_channel="",
            source_channel="C123",
            observer_result=result,
            actions=[],
            actions_filtered=[],
        )

        client.chat_postMessage.assert_not_called()


# ── send_intervention_probability_debug_log 테스트 ────────

class TestSendInterventionProbabilityDebugLog:
    """확률 판단 디버그 로그 테스트"""

    def test_sends_passed_log_with_blocks(self):
        """통과 시 Block Kit 로그"""
        client = MagicMock()

        send_intervention_probability_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            importance=8,
            time_factor=0.78,
            freq_factor=0.77,
            probability=0.6,
            final_score=0.48,
            threshold=0.3,
            passed=True,
        )

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "blocks" in call_kwargs
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "C123" in blocks_str
        assert "8/10" in blocks_str

    def test_sends_blocked_log_with_blocks(self):
        """차단 시 Block Kit 로그"""
        client = MagicMock()

        send_intervention_probability_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            importance=3,
            time_factor=0.2,
            freq_factor=0.5,
            probability=0.1,
            final_score=0.03,
            threshold=0.3,
            passed=False,
        )

        call_kwargs = client.chat_postMessage.call_args[1]
        assert "blocks" in call_kwargs

    def test_skips_when_no_debug_channel(self):
        """디버그 채널 미설정이면 전송 안 함"""
        client = MagicMock()

        send_intervention_probability_debug_log(
            client=client,
            debug_channel="",
            source_channel="C123",
            importance=5,
            time_factor=0.5,
            freq_factor=1.0,
            probability=0.5,
            final_score=0.25,
            threshold=0.3,
            passed=False,
        )

        client.chat_postMessage.assert_not_called()


# ── run_channel_pipeline 통합 테스트 ─────────────────

class FakeObserver:
    """ChannelObserver mock (digest + judge)"""

    def __init__(
        self,
        judge_result: JudgeResult | None = None,
        digest_result: DigestResult | None = None,
    ):
        self.judge_result = judge_result or JudgeResult(
            importance=4, reaction_type="none",
        )
        self.digest_result = digest_result or DigestResult(
            digest="digest 결과", token_count=100,
        )
        self.judge_call_count = 0
        self.digest_call_count = 0

    async def judge(self, **kwargs) -> JudgeResult | None:
        self.judge_call_count += 1
        return self.judge_result

    async def digest(self, **kwargs) -> DigestResult | None:
        self.digest_call_count += 1
        return self.digest_result


def _fill_buffer(store: ChannelStore, channel_id: str, n: int = 10):
    for i in range(n):
        store.append_pending(channel_id, {
            "ts": f"100{i}.000",
            "user": f"U{i}",
            "text": f"테스트 메시지 {i}번 - " + "내용 " * 20,
        })


class TestRunChannelPipeline:
    """소화/판단 분리 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_intervene_sends_message_via_llm(self, tmp_path):
        """판단 → 개입 → LLM 호출 → 슬랙 메시지 발송 흐름"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="아이고, 무슨 소동이오?",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "이런 일이 벌어지다니, 놀랍구려."

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            intervention_threshold=0.0,  # 항상 통과
            llm_call=mock_llm_call,
        )

        client.chat_postMessage.assert_called()
        call_args_list = client.chat_postMessage.call_args_list
        sent_texts = [c[1]["text"] for c in call_args_list]
        # LLM 생성 응답이 발송됨
        assert any("놀랍구려" in t for t in sent_texts)

    @pytest.mark.asyncio
    async def test_intervene_fallback_without_llm(self, tmp_path):
        """llm_call 없으면 직접 발송 (폴백)"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="아이고, 무슨 소동이오?",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            intervention_threshold=0.0,
            # llm_call 없음 → 폴백
        )

        client.chat_postMessage.assert_called()
        call_args_list = client.chat_postMessage.call_args_list
        sent_texts = [c[1]["text"] for c in call_args_list]
        assert any("무슨 소동" in t for t in sent_texts)

    @pytest.mark.asyncio
    async def test_react_sends_emoji(self, tmp_path):
        """판단 → 이모지 리액션 발송 흐름"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=5,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="laughing",
        ))

        client = MagicMock()
        client.reactions_add = MagicMock(return_value={"ok": True})

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
        )

        client.reactions_add.assert_called_once_with(
            channel="C123",
            timestamp="1001.000",
            name="laughing",
        )

    @pytest.mark.asyncio
    async def test_probability_blocks_low_score(self, tmp_path):
        """확률 점수가 임계치 미만이면 메시지 개입이 차단됨"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        # 방금 개입한 이력 추가 → minutes_since_last ≈ 0 → probability ≈ 0
        history.record("C123")
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=3,  # 낮은 중요도
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입 메시지",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "LLM 응답"

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            intervention_threshold=0.5,  # 높은 임계치
            llm_call=mock_llm_call,
        )

        # 채널에 메시지 발송 없음 (디버그 로그는 제외)
        channel_calls = [
            c for c in client.chat_postMessage.call_args_list
            if c[1].get("channel") == "C123"
        ]
        assert len(channel_calls) == 0

    @pytest.mark.asyncio
    async def test_high_importance_passes(self, tmp_path):
        """높은 중요도 + 충분한 시간 경과면 개입 통과"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        # 이력 없음 → minutes_since_last = inf → probability ≈ 1.0
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=9,  # 높은 중요도
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="중요한 대화",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "중요한 응답입니다."

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            intervention_threshold=0.3,
            llm_call=mock_llm_call,
        )

        # LLM 응답이 채널에 발송됨
        channel_calls = [
            c for c in client.chat_postMessage.call_args_list
            if c[1].get("channel") == "C123"
        ]
        assert len(channel_calls) >= 1
        assert any("중요한 응답" in c[1]["text"] for c in channel_calls)

    @pytest.mark.asyncio
    async def test_intervene_records_history(self, tmp_path):
        """개입 성공 후 이력이 기록됨"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=9,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "응답"

        assert history.recent_count("C123") == 0

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            intervention_threshold=0.0,
            llm_call=mock_llm_call,
        )

        assert history.recent_count("C123") == 1

    @pytest.mark.asyncio
    async def test_no_reaction_skips_intervention(self, tmp_path):
        """반응이 none이면 개입 없음"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=2,
            reaction_type="none",
        ))

        client = MagicMock()

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
        )

        client.chat_postMessage.assert_not_called()
        client.reactions_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_debug_log_sent(self, tmp_path):
        """디버그 채널이 설정되면 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        history = InterventionHistory(base_dir=tmp_path)
        _fill_buffer(store, "C123")

        observer = FakeObserver(judge_result=JudgeResult(
            importance=3,
            reaction_type="none",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            debug_channel="C_DEBUG",
        )

        # 디버그 로그가 전송됨
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_DEBUG"


# ── send_collect_debug_log 테스트 ────────────────────────

class TestSendCollectDebugLog:
    """메시지 수집 디버그 로그"""

    def test_sends_log_with_blocks(self):
        """수집 시 Block Kit 로그 전송"""
        client = MagicMock()

        send_collect_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=200,
            threshold=500,
            message_text="안녕하세요",
            user="U001",
        )

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "blocks" in call_kwargs
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "C123" in blocks_str
        assert "200/500" in blocks_str
        assert "안녕하세요" in blocks_str

    def test_shows_trigger_when_threshold_reached(self):
        """임계치 도달 시 소화 트리거 표시"""
        client = MagicMock()

        send_collect_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=500,
            threshold=500,
            message_text="길이 넘는 메시지",
            user="U001",
        )

        call_kwargs = client.chat_postMessage.call_args[1]
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "소화 트리거" in blocks_str

    def test_shows_thread_label(self):
        """스레드 메시지면 '스레드' 라벨 표시"""
        client = MagicMock()

        send_collect_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=100,
            threshold=500,
            message_text="스레드 답글",
            user="U002",
            is_thread=True,
        )

        call_kwargs = client.chat_postMessage.call_args[1]
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "스레드" in blocks_str

    def test_skips_when_no_debug_channel(self):
        """디버그 채널 미설정이면 전송 안 함"""
        client = MagicMock()

        send_collect_debug_log(
            client=client,
            debug_channel="",
            source_channel="C123",
            buffer_tokens=100,
            threshold=500,
        )

        client.chat_postMessage.assert_not_called()

    def test_truncates_long_message(self):
        """80자 초과 메시지는 잘림"""
        client = MagicMock()
        long_text = "가" * 100

        send_collect_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=100,
            threshold=500,
            message_text=long_text,
            user="U001",
        )

        call_kwargs = client.chat_postMessage.call_args[1]
        # fallback text 또는 blocks 내에 ... 포함
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "..." in blocks_str


# ── send_digest_skip_debug_log 테스트 ────────────────────

class TestSendDigestSkipDebugLog:
    """소화 스킵 디버그 로그"""

    def test_sends_skip_log_with_blocks(self):
        """스킵 시 Block Kit 로그 전송"""
        client = MagicMock()

        send_digest_skip_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=200,
            threshold=500,
        )

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "blocks" in call_kwargs
        blocks_str = json.dumps(call_kwargs["blocks"], ensure_ascii=False)
        assert "소화 스킵" in blocks_str
        assert "200" in blocks_str
        assert "500" in blocks_str

    def test_skips_when_no_debug_channel(self):
        """디버그 채널 미설정이면 전송 안 함"""
        client = MagicMock()

        send_digest_skip_debug_log(
            client=client,
            debug_channel="",
            source_channel="C123",
            buffer_tokens=200,
            threshold=500,
        )

        client.chat_postMessage.assert_not_called()
