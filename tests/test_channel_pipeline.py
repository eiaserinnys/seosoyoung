"""채널 소화 파이프라인 통합 테스트"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.channel_intervention import CooldownManager
from seosoyoung.memory.channel_observer import (
    ChannelObserverResult,
    DigestCompressorResult,
)
from seosoyoung.memory.channel_pipeline import digest_channel, respond_in_intervention_mode
from seosoyoung.memory.channel_prompts import (
    build_intervention_mode_prompt,
    INTERVENTION_MODE_SYSTEM_PROMPT,
)
from seosoyoung.memory.channel_store import ChannelStore


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


@pytest.fixture
def channel_id():
    return "C_TEST_CHANNEL"


def _fill_buffer(store: ChannelStore, channel_id: str, n: int = 10):
    """버퍼에 테스트 메시지를 채운다."""
    for i in range(n):
        store.append_channel_message(channel_id, {
            "ts": f"100{i}.000",
            "user": f"U{i}",
            "text": f"테스트 메시지 {i}번 - " + "내용 " * 20,
        })
    store.append_thread_message(channel_id, "1000.000", {
        "ts": "1000.001",
        "user": "U99",
        "text": "스레드 답글",
    })


class FakeObserver:
    """ChannelObserver mock"""

    def __init__(self, result: ChannelObserverResult | None = None):
        self.result = result or ChannelObserverResult(
            digest="새로운 digest 결과",
            importance=4,
            reaction_type="none",
        )
        self.call_count = 0

    async def observe(self, **kwargs) -> ChannelObserverResult | None:
        self.call_count += 1
        return self.result


class FakeCompressor:
    """DigestCompressor mock"""

    def __init__(self, result: DigestCompressorResult | None = None):
        self.result = result or DigestCompressorResult(
            digest="압축된 digest",
            token_count=100,
        )
        self.call_count = 0

    async def compress(self, **kwargs) -> DigestCompressorResult | None:
        self.call_count += 1
        return self.result


class TestDigestChannel:
    """소화 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_skip_when_buffer_below_threshold(self, store, channel_id):
        """버퍼 토큰이 임계치 미만이면 스킵"""
        store.append_channel_message(channel_id, {
            "ts": "1.1", "user": "U1", "text": "짧은 메시지",
        })
        observer = FakeObserver()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=99999,
        )

        assert result is None
        assert observer.call_count == 0
        # 버퍼는 그대로 유지
        assert len(store.load_channel_buffer(channel_id)) == 1

    @pytest.mark.asyncio
    async def test_digest_success(self, store, channel_id):
        """정상 소화: Observer 호출 → digest 저장 → 버퍼 비우기"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,  # 낮은 임계치로 즉시 트리거
        )

        assert result is not None
        assert result.digest == "새로운 digest 결과"
        assert result.importance == 4
        assert observer.call_count == 1

        # digest가 저장되었는지 확인
        saved = store.get_digest(channel_id)
        assert saved is not None
        assert saved["content"] == "새로운 digest 결과"

        # 버퍼가 비워졌는지 확인
        assert len(store.load_channel_buffer(channel_id)) == 0
        assert len(store.load_all_thread_buffers(channel_id)) == 0

    @pytest.mark.asyncio
    async def test_digest_with_existing_digest(self, store, channel_id):
        """기존 digest가 있을 때 Observer에 전달되는지 확인"""
        store.save_digest(channel_id, "이전 digest", {"token_count": 50})
        _fill_buffer(store, channel_id)

        observer = FakeObserver()
        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is not None
        assert observer.call_count == 1

    @pytest.mark.asyncio
    async def test_digest_triggers_compressor(self, store, channel_id):
        """digest 토큰이 임계치 초과하면 Compressor 호출"""
        _fill_buffer(store, channel_id)

        long_digest = "장문의 digest " * 500
        observer = FakeObserver(ChannelObserverResult(
            digest=long_digest,
            importance=3,
            reaction_type="none",
        ))
        compressor = FakeCompressor()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
            compressor=compressor,
            digest_max_tokens=10,  # 매우 낮은 임계치
            digest_target_tokens=5,
        )

        assert result is not None
        assert compressor.call_count == 1
        # 압축된 digest가 저장됨
        saved = store.get_digest(channel_id)
        assert saved["content"] == "압축된 digest"

    @pytest.mark.asyncio
    async def test_digest_no_compressor_when_under_threshold(self, store, channel_id):
        """digest 토큰이 임계치 이하면 Compressor 호출 안 함"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver()
        compressor = FakeCompressor()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
            compressor=compressor,
            digest_max_tokens=999999,
        )

        assert result is not None
        assert compressor.call_count == 0

    @pytest.mark.asyncio
    async def test_observer_returns_none(self, store, channel_id):
        """Observer가 None을 반환하면 파이프라인도 None"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver(result=None)
        observer.result = None  # 명시적 None 설정

        class NoneObserver:
            call_count = 0
            async def observe(self, **kwargs):
                self.call_count += 1
                return None

        none_observer = NoneObserver()
        result = await digest_channel(
            store=store,
            observer=none_observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is None
        # 버퍼는 비우지 않음 (실패했으므로)
        assert len(store.load_channel_buffer(channel_id)) > 0

    @pytest.mark.asyncio
    async def test_reaction_returned(self, store, channel_id):
        """반응 정보가 결과에 포함되는지 확인"""
        _fill_buffer(store, channel_id)

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 결과",
            importance=7,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="laughing",
        ))

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is not None
        assert result.reaction_type == "react"
        assert result.reaction_target == "1001.000"
        assert result.reaction_content == "laughing"

    @pytest.mark.asyncio
    async def test_meta_updated(self, store, channel_id):
        """digest meta에 토큰 수와 중요도가 기록되는지"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 내용",
            importance=6,
            reaction_type="none",
        ))

        await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        saved = store.get_digest(channel_id)
        meta = saved["meta"]
        assert "token_count" in meta
        assert "last_importance" in meta
        assert meta["last_importance"] == 6


# ── 개입 모드 프롬프트 테스트 ──────────────────────────

class TestInterventionModePrompt:
    """개입 모드 프롬프트 빌더 테스트"""

    def test_system_prompt_exists(self):
        """INTERVENTION_MODE_SYSTEM_PROMPT 상수가 존재"""
        assert INTERVENTION_MODE_SYSTEM_PROMPT
        assert "서소영" in INTERVENTION_MODE_SYSTEM_PROMPT

    def test_build_prompt_includes_remaining_turns(self):
        """남은 턴이 프롬프트에 포함"""
        prompt = build_intervention_mode_prompt(
            remaining_turns=5,
            channel_id="C123",
            new_messages=[{"ts": "1.1", "user": "U1", "text": "안녕"}],
            digest="채널 다이제스트",
        )
        assert "5" in prompt

    def test_build_prompt_includes_digest(self):
        """다이제스트가 프롬프트에 포함"""
        prompt = build_intervention_mode_prompt(
            remaining_turns=3,
            channel_id="C123",
            new_messages=[{"ts": "1.1", "user": "U1", "text": "안녕"}],
            digest="테스트 다이제스트 내용",
        )
        assert "테스트 다이제스트 내용" in prompt

    def test_build_prompt_includes_messages(self):
        """새 메시지가 프롬프트에 포함"""
        prompt = build_intervention_mode_prompt(
            remaining_turns=3,
            channel_id="C123",
            new_messages=[
                {"ts": "1.1", "user": "U1", "text": "첫 번째 메시지"},
                {"ts": "1.2", "user": "U2", "text": "두 번째 메시지"},
            ],
            digest="다이제스트",
        )
        assert "첫 번째 메시지" in prompt
        assert "두 번째 메시지" in prompt

    def test_last_turn_includes_farewell_instruction(self):
        """마지막 턴에는 마무리 지시가 포함"""
        prompt = build_intervention_mode_prompt(
            remaining_turns=1,
            channel_id="C123",
            new_messages=[{"ts": "1.1", "user": "U1", "text": "안녕"}],
            digest="다이제스트",
        )
        # 마지막 턴이므로 마무리 관련 지시가 있어야 함
        assert "마지막" in prompt or "마무리" in prompt

    def test_not_last_turn_no_farewell(self):
        """마지막 턴이 아니면 마무리 지시 없음"""
        prompt = build_intervention_mode_prompt(
            remaining_turns=5,
            channel_id="C123",
            new_messages=[{"ts": "1.1", "user": "U1", "text": "안녕"}],
            digest="다이제스트",
        )
        assert "마지막" not in prompt


# ── respond_in_intervention_mode 테스트 ────────────────

class TestRespondInInterventionMode:
    """개입 모드 반응 함수 테스트"""

    @pytest.mark.asyncio
    async def test_responds_and_consumes_turn(self, tmp_path):
        """개입 모드 반응: LLM 호출 + 슬랙 발송 + 턴 소모"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        # 버퍼에 메시지 추가
        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "테스트 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})

        # LLM mock
        mock_llm = AsyncMock(return_value="아이고, 재미있는 이야기로군요.")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
        )

        # 슬랙에 메시지 발송됨
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert "재미있는" in call_kwargs["text"]

        # 턴이 소모됨
        assert cooldown.get_remaining_turns("C123") == 2

    @pytest.mark.asyncio
    async def test_last_turn_transitions_to_idle(self, tmp_path):
        """마지막 턴이면 idle로 전환"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=1)

        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(return_value="이만 물러가겠소.")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
        )

        assert cooldown.is_active("C123") is False
        assert cooldown.can_intervene("C123") is False  # 쿨다운 진입

    @pytest.mark.asyncio
    async def test_llm_receives_correct_prompt(self, tmp_path):
        """LLM에 올바른 프롬프트가 전달되는지 확인"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=5)

        store.save_digest("C123", "기존 다이제스트", {"token_count": 100})
        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "새 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(return_value="응답")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
        )

        # LLM이 호출됨
        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        system_prompt = call_args[1].get("system_prompt") or call_args[0][0]
        user_prompt = call_args[1].get("user_prompt") or call_args[0][1]

        # 시스템 프롬프트에 서소영 관련 내용
        assert "서소영" in system_prompt
        # 유저 프롬프트에 다이제스트와 메시지
        assert "기존 다이제스트" in user_prompt
        assert "새 메시지" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_buffer_skips(self, tmp_path):
        """버퍼가 비어있으면 반응 스킵"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=5)

        client = MagicMock()
        mock_llm = AsyncMock(return_value="응답")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
        )

        # 빈 버퍼: LLM 호출 안 됨
        mock_llm.assert_not_called()
        client.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_buffer_after_response(self, tmp_path):
        """반응 후 채널 버퍼를 비움"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=5)

        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(return_value="응답")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
        )

        assert len(store.load_channel_buffer("C123")) == 0

    @pytest.mark.asyncio
    async def test_debug_log_sent_on_respond(self, tmp_path):
        """개입 반응 시 디버그 채널에 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "트리거 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(return_value="응답입니다.")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
            debug_channel="C_DEBUG",
        )

        # chat_postMessage 호출: 1) 채널 응답 + 2) 디버그 로그
        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        assert len(debug_calls) >= 1
        debug_text = debug_calls[0][1]["text"]
        assert "개입 모드 반응" in debug_text
        assert "응답입니다" in debug_text
        assert "트리거 메시지" in debug_text

    @pytest.mark.asyncio
    async def test_debug_log_exit_on_last_turn(self, tmp_path):
        """마지막 턴에 종료 디버그 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=1)

        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(return_value="이만 물러가겠소.")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
            debug_channel="C_DEBUG",
        )

        # 디버그 로그 중 종료 로그 확인
        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        debug_texts = [c[1]["text"] for c in debug_calls]
        assert any("개입 모드 종료" in t for t in debug_texts)

    @pytest.mark.asyncio
    async def test_debug_log_on_llm_error(self, tmp_path):
        """LLM 실패 시 에러 디버그 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        store.append_channel_message("C123", {
            "ts": "1.1", "user": "U1", "text": "메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        mock_llm = AsyncMock(side_effect=Exception("API timeout"))

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            llm_call=mock_llm,
            debug_channel="C_DEBUG",
        )

        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        assert len(debug_calls) >= 1
        assert "오류" in debug_calls[0][1]["text"]
        assert "API timeout" in debug_calls[0][1]["text"]
