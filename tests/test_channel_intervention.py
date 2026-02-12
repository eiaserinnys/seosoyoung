"""채널 개입(intervention) 단위 테스트

Phase 3: 마크업 파서 + 슬랙 발송 + 쿨다운 로직 + 통합 파이프라인 테스트
"""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.channel_intervention import (
    InterventionAction,
    parse_intervention_markup,
    execute_interventions,
    CooldownManager,
    send_collect_debug_log,
    send_debug_log,
    send_digest_skip_debug_log,
)
from seosoyoung.memory.channel_observer import ChannelObserverResult
from seosoyoung.memory.channel_pipeline import run_digest_and_intervene
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


# ── CooldownManager ──────────────────────────────────────

class TestCooldownManager:
    """쿨다운 관리 테스트"""

    def test_message_allowed_when_no_previous(self, tmp_path):
        """이전 기록이 없으면 허용"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=1800)
        assert cm.can_intervene("C123") is True

    def test_message_blocked_within_cooldown(self, tmp_path):
        """쿨다운 내에서는 차단"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=1800)
        cm.record_intervention("C123")
        assert cm.can_intervene("C123") is False

    def test_message_allowed_after_cooldown(self, tmp_path):
        """쿨다운 만료 후 허용"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        cm.record_intervention("C123")
        # cooldown_sec=0이므로 즉시 허용
        assert cm.can_intervene("C123") is True

    def test_react_always_allowed(self, tmp_path):
        """이모지 리액션은 쿨다운 대상 아님"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=1800)
        cm.record_intervention("C123")
        assert cm.can_react("C123") is True

    def test_record_updates_timestamp(self, tmp_path):
        """기록 시 타임스탬프가 업데이트됨"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=1800)
        cm.record_intervention("C123")

        meta_path = tmp_path / "channel" / "C123" / "intervention.meta.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "last_intervention_at" in data

    def test_filter_actions_by_cooldown(self, tmp_path):
        """쿨다운에 걸린 메시지 액션은 필터링, 리액션은 유지"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=1800)
        cm.record_intervention("C123")

        actions = [
            InterventionAction(type="message", target="channel", content="개입"),
            InterventionAction(type="react", target="1.1", content="smile"),
        ]
        filtered = cm.filter_actions("C123", actions)
        assert len(filtered) == 1
        assert filtered[0].type == "react"


# ── CooldownManager 개입 모드 상태 머신 ─────────────────

class TestCooldownManagerInterventionMode:
    """개입 모드 상태 머신 테스트 (idle ↔ active)"""

    def test_initial_state_is_idle(self, tmp_path):
        """초기 상태는 idle"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        assert cm.is_active("C123") is False
        assert cm.get_remaining_turns("C123") == 0

    def test_enter_intervention_mode(self, tmp_path):
        """enter_intervention_mode로 active 상태 전환"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm.enter_intervention_mode("C123", max_turns=5)

        assert cm.is_active("C123") is True
        assert cm.get_remaining_turns("C123") == 5

    def test_consume_turn_decrements(self, tmp_path):
        """consume_turn은 턴을 1 소모하고 남은 턴을 반환"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm.enter_intervention_mode("C123", max_turns=3)

        remaining = cm.consume_turn("C123")
        assert remaining == 2
        assert cm.get_remaining_turns("C123") == 2

    def test_consume_turn_to_zero_transitions_to_idle(self, tmp_path):
        """턴이 0이 되면 idle로 전환되고 쿨다운 기록"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm.enter_intervention_mode("C123", max_turns=1)

        remaining = cm.consume_turn("C123")
        assert remaining == 0
        assert cm.is_active("C123") is False
        # 쿨다운이 기록되어야 함
        assert cm.can_intervene("C123") is False

    def test_consume_turn_multiple(self, tmp_path):
        """여러 턴 소모"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm.enter_intervention_mode("C123", max_turns=3)

        assert cm.consume_turn("C123") == 2
        assert cm.consume_turn("C123") == 1
        assert cm.consume_turn("C123") == 0
        assert cm.is_active("C123") is False

    def test_consume_turn_when_idle_returns_zero(self, tmp_path):
        """idle 상태에서 consume_turn은 0 반환"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        remaining = cm.consume_turn("C123")
        assert remaining == 0

    def test_filter_actions_active_allows_message(self, tmp_path):
        """active 모드에서는 message 액션도 통과"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=9999)
        cm.enter_intervention_mode("C123", max_turns=5)

        actions = [
            InterventionAction(type="message", target="channel", content="개입"),
            InterventionAction(type="react", target="1.1", content="smile"),
        ]
        filtered = cm.filter_actions("C123", actions)
        assert len(filtered) == 2

    def test_different_channels_independent(self, tmp_path):
        """채널마다 독립적인 상태"""
        cm = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm.enter_intervention_mode("C123", max_turns=3)

        assert cm.is_active("C123") is True
        assert cm.is_active("C456") is False

    def test_meta_persists_mode(self, tmp_path):
        """상태가 파일에 저장되어 새 인스턴스에서도 유지"""
        cm1 = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cm1.enter_intervention_mode("C123", max_turns=5)

        # 새 인스턴스로 상태 확인
        cm2 = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        assert cm2.is_active("C123") is True
        assert cm2.get_remaining_turns("C123") == 5


# ── send_debug_log ───────────────────────────────────────

class TestSendDebugLog:
    """디버그 로그 발송 테스트"""

    @pytest.mark.asyncio
    async def test_sends_to_debug_channel(self):
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
        assert "C123" in call_kwargs["text"]
        assert "7" in call_kwargs["text"]  # importance

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


# ── run_digest_and_intervene 통합 테스트 ─────────────────

class FakeObserver:
    """ChannelObserver mock"""

    def __init__(self, result: ChannelObserverResult | None = None):
        self.result = result
        self.call_count = 0

    async def observe(self, **kwargs) -> ChannelObserverResult | None:
        self.call_count += 1
        return self.result


def _fill_buffer(store: ChannelStore, channel_id: str, n: int = 10):
    for i in range(n):
        store.append_channel_message(channel_id, {
            "ts": f"100{i}.000",
            "user": f"U{i}",
            "text": f"테스트 메시지 {i}번 - " + "내용 " * 20,
        })


class TestRunDigestAndIntervene:
    """소화 + 개입 통합 파이프라인 테스트"""

    @pytest.mark.asyncio
    async def test_intervene_sends_message_via_llm(self, tmp_path):
        """소화 → 개입 판단 → LLM 호출 → 슬랙 메시지 발송 흐름"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 결과",
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="아이고, 무슨 소동이오?",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "이런 일이 벌어지다니, 놀랍구려."

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
            llm_call=mock_llm_call,
        )

        client.chat_postMessage.assert_called()
        call_args_list = client.chat_postMessage.call_args_list
        sent_texts = [c[1]["text"] for c in call_args_list]
        # LLM 생성 응답이 발송됨 (Observer 텍스트가 아님)
        assert any("놀랍구려" in t for t in sent_texts)

    @pytest.mark.asyncio
    async def test_intervene_fallback_without_llm(self, tmp_path):
        """llm_call 없으면 Observer 텍스트로 직접 발송 (폴백)"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 결과",
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="아이고, 무슨 소동이오?",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
            # llm_call 없음 → 폴백
        )

        client.chat_postMessage.assert_called()
        call_args_list = client.chat_postMessage.call_args_list
        sent_texts = [c[1]["text"] for c in call_args_list]
        assert any("무슨 소동" in t for t in sent_texts)

    @pytest.mark.asyncio
    async def test_react_sends_emoji(self, tmp_path):
        """소화 → 이모지 리액션 발송 흐름"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰",
            importance=5,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="laughing",
        ))

        client = MagicMock()
        client.reactions_add = MagicMock(return_value={"ok": True})

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
        )

        client.reactions_add.assert_called_once_with(
            channel="C123",
            timestamp="1001.000",
            name="laughing",
        )

    @pytest.mark.asyncio
    async def test_cooldown_blocks_message(self, tmp_path):
        """쿨다운 중이면 메시지 개입이 스킵됨"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=9999)
        cooldown.record_intervention("C123")
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰",
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입 메시지",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "LLM 응답"

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
            llm_call=mock_llm_call,
        )

        # 메시지 발송 호출 없음 (쿨다운)
        client.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_cooldown_allows_react_while_blocking_message(self, tmp_path):
        """쿨다운 중에도 이모지 리액션은 허용"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=9999)
        cooldown.record_intervention("C123")
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰",
            importance=5,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="eyes",
        ))

        client = MagicMock()
        client.reactions_add = MagicMock(return_value={"ok": True})

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
        )

        client.reactions_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_reaction_skips_intervention(self, tmp_path):
        """반응이 none이면 개입 없음"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="평범한 대화",
            importance=2,
            reaction_type="none",
        ))

        client = MagicMock()

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
        )

        client.chat_postMessage.assert_not_called()
        client.reactions_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_intervene_enters_intervention_mode(self, tmp_path):
        """소화 → 개입 시 개입 모드 진입"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 결과",
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="무슨 일이오?",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        async def mock_llm_call(system_prompt, user_prompt):
            return "LLM 개입 응답"

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
            max_intervention_turns=5,
            debug_channel="C_DEBUG",
            llm_call=mock_llm_call,
        )

        # 개입 후 개입 모드에 진입해야 함
        assert cooldown.is_active("C123") is True
        assert cooldown.get_remaining_turns("C123") == 5

        # 디버그 채널에 개입 모드 진입 로그가 전송됨
        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        assert len(debug_calls) >= 1
        debug_texts = [c[1]["text"] for c in debug_calls]
        assert any("개입 모드 진입" in t for t in debug_texts)

    @pytest.mark.asyncio
    async def test_debug_log_sent(self, tmp_path):
        """디버그 채널이 설정되면 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=0)
        _fill_buffer(store, "C123")

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰",
            importance=3,
            reaction_type="none",
        ))

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        await run_digest_and_intervene(
            store=store,
            observer=observer,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            buffer_threshold=1,
            debug_channel="C_DEBUG",
        )

        # 디버그 로그가 전송됨
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_DEBUG"


# ── send_collect_debug_log 테스트 ────────────────────────

class TestSendCollectDebugLog:
    """메시지 수집 디버그 로그"""

    def test_sends_log_with_buffer_status(self):
        """수집 시 버퍼 상태 포함 로그 전송"""
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
        text = client.chat_postMessage.call_args[1]["text"]
        assert "채널 수집" in text
        assert "C123" in text
        assert "200/500" in text
        assert "안녕하세요" in text

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

        text = client.chat_postMessage.call_args[1]["text"]
        assert "소화 트리거" in text

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

        text = client.chat_postMessage.call_args[1]["text"]
        assert "스레드" in text

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

        text = client.chat_postMessage.call_args[1]["text"]
        assert "..." in text


# ── send_digest_skip_debug_log 테스트 ────────────────────

class TestSendDigestSkipDebugLog:
    """소화 스킵 디버그 로그"""

    def test_sends_skip_log(self):
        """스킵 시 로그 전송"""
        client = MagicMock()

        send_digest_skip_debug_log(
            client=client,
            debug_channel="C_DEBUG",
            source_channel="C123",
            buffer_tokens=200,
            threshold=500,
        )

        client.chat_postMessage.assert_called_once()
        text = client.chat_postMessage.call_args[1]["text"]
        assert "소화 스킵" in text
        assert "200" in text
        assert "500" in text

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
