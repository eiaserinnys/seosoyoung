"""채널 소화/판단 파이프라인 통합 테스트"""

from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from seosoyoung.memory.channel_intervention import CooldownManager
from seosoyoung.memory.channel_observer import (
    DigestCompressorResult,
    DigestResult,
    JudgeResult,
)
from seosoyoung.memory.channel_pipeline import (
    run_channel_pipeline,
    respond_in_intervention_mode,
)
from seosoyoung.memory.channel_prompts import (
    build_intervention_mode_prompt,
    get_intervention_mode_system_prompt,
)
from seosoyoung.memory.channel_store import ChannelStore


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


@pytest.fixture
def channel_id():
    return "C_TEST_CHANNEL"


def _fill_pending(store: ChannelStore, channel_id: str, n: int = 10):
    """pending 버퍼에 테스트 메시지를 채운다."""
    for i in range(n):
        store.append_pending(channel_id, {
            "ts": f"100{i}.000",
            "user": f"U{i}",
            "text": f"테스트 메시지 {i}번 - " + "내용 " * 20,
        })


def _fill_judged(store: ChannelStore, channel_id: str, n: int = 5):
    """judged 버퍼에 테스트 메시지를 채운다."""
    messages = []
    for i in range(n):
        messages.append({
            "ts": f"200{i}.000",
            "user": f"U{i}",
            "text": f"판단 완료 메시지 {i}번 - " + "내용 " * 20,
        })
    store.append_judged(channel_id, messages)


class FakeObserver:
    """ChannelObserver mock (digest + judge)"""

    def __init__(
        self,
        digest_result: DigestResult | None = None,
        judge_result: JudgeResult | None = None,
    ):
        self.digest_result = digest_result or DigestResult(
            digest="새로운 digest 결과",
            token_count=100,
        )
        self.judge_result = judge_result or JudgeResult(
            importance=4,
            reaction_type="none",
        )
        self.digest_call_count = 0
        self.judge_call_count = 0
        self.judge_kwargs = {}

    async def digest(self, **kwargs) -> DigestResult | None:
        self.digest_call_count += 1
        return self.digest_result

    async def judge(self, **kwargs) -> JudgeResult | None:
        self.judge_call_count += 1
        self.judge_kwargs = kwargs
        return self.judge_result


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


# ── run_channel_pipeline 테스트 ──────────────────────────

class TestRunChannelPipeline:
    """소화/판단 분리 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_skip_when_pending_below_threshold_a(self, store, channel_id):
        """pending 토큰이 threshold_A 미만이면 스킵"""
        store.append_pending(channel_id, {
            "ts": "1.1", "user": "U1", "text": "짧은 메시지",
        })
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=99999,
        )

        assert observer.judge_call_count == 0
        assert observer.digest_call_count == 0
        # pending은 그대로 유지
        assert len(store.load_pending(channel_id)) == 1

    @pytest.mark.asyncio
    async def test_judge_called_when_above_threshold_a(self, store, channel_id):
        """pending이 threshold_A 이상이면 judge 호출"""
        _fill_pending(store, channel_id)
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=999999,
        )

        assert observer.judge_call_count == 1
        # digest는 threshold_b 이하이므로 호출 안 됨
        assert observer.digest_call_count == 0

    @pytest.mark.asyncio
    async def test_pending_moved_to_judged_after_pipeline(self, store, channel_id):
        """파이프라인 실행 후 pending이 judged로 이동"""
        _fill_pending(store, channel_id, n=5)
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=999999,
        )

        # pending은 비어야 하고 judged에 이동
        assert len(store.load_pending(channel_id)) == 0
        assert len(store.load_judged(channel_id)) == 5

    @pytest.mark.asyncio
    async def test_digest_triggered_when_above_threshold_b(self, store, channel_id):
        """judged+pending이 threshold_B 초과하면 digest 호출"""
        _fill_judged(store, channel_id, n=10)
        _fill_pending(store, channel_id, n=10)
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=1,  # 매우 낮은 임계치
        )

        assert observer.digest_call_count == 1
        assert observer.judge_call_count == 1
        # digest 저장 확인
        saved = store.get_digest(channel_id)
        assert saved is not None
        assert saved["content"] == "새로운 digest 결과"

    @pytest.mark.asyncio
    async def test_digest_clears_judged(self, store, channel_id):
        """digest 편입 후 judged가 비워짐"""
        _fill_judged(store, channel_id, n=5)
        _fill_pending(store, channel_id, n=5)
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=1,
        )

        # digest 편입으로 judged 비워진 후, pending이 judged로 이동
        judged = store.load_judged(channel_id)
        assert len(judged) == 5  # pending에서 이동된 것만

    @pytest.mark.asyncio
    async def test_digest_compressor_triggered(self, store, channel_id):
        """digest 토큰이 max 초과하면 compressor 호출"""
        _fill_judged(store, channel_id, n=5)
        _fill_pending(store, channel_id, n=5)

        long_digest = DigestResult(
            digest="장문의 digest " * 500,
            token_count=20000,
        )
        observer = FakeObserver(digest_result=long_digest)
        compressor = FakeCompressor()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=1,
            compressor=compressor,
            digest_max_tokens=10,
            digest_target_tokens=5,
        )

        assert compressor.call_count == 1
        saved = store.get_digest(channel_id)
        assert saved["content"] == "압축된 digest"

    @pytest.mark.asyncio
    async def test_no_compressor_when_under_max(self, store, channel_id):
        """digest 토큰이 max 이하면 compressor 호출 안 함"""
        _fill_judged(store, channel_id, n=5)
        _fill_pending(store, channel_id, n=5)
        observer = FakeObserver()
        compressor = FakeCompressor()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=1,
            compressor=compressor,
            digest_max_tokens=999999,
        )

        assert compressor.call_count == 0

    @pytest.mark.asyncio
    async def test_judge_returns_none(self, store, channel_id):
        """judge가 None을 반환하면 파이프라인 중단"""
        _fill_pending(store, channel_id)

        observer = FakeObserver()
        observer.judge_result = None
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
        )

        # pending은 이동되지 않음 (judge 실패)
        assert len(store.load_pending(channel_id)) > 0

    @pytest.mark.asyncio
    async def test_react_action_executed(self, store, channel_id):
        """judge가 react를 반환하면 이모지 리액션 실행"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=7,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="laughing",
        ))
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
        )

        # 이모지 리액션 API 호출 확인
        client.reactions_add.assert_called_once_with(
            channel=channel_id,
            name="laughing",
            timestamp="1001.000",
        )

    @pytest.mark.asyncio
    async def test_intervene_action_with_llm(self, store, channel_id):
        """judge가 intervene을 반환하면 LLM으로 응답 생성"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="1005.000",
            reaction_content="이 대화에 끼어들어야 할 것 같습니다",
        ))
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=0)
        mock_llm = AsyncMock(return_value="흥미로운 이야기로군요.")

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            llm_call=mock_llm,
        )

        # LLM이 호출되고 슬랙에 발송됨
        mock_llm.assert_called_once()
        client.chat_postMessage.assert_called()

    @pytest.mark.asyncio
    async def test_intervene_without_llm_fallback(self, store, channel_id):
        """llm_call이 없으면 직접 발송"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="직접 발송 텍스트",
        ))
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=0)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            llm_call=None,
        )

        client.chat_postMessage.assert_called()

    @pytest.mark.asyncio
    async def test_debug_log_sent(self, store, channel_id):
        """디버그 채널에 로그 전송"""
        _fill_pending(store, channel_id)
        observer = FakeObserver()
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            debug_channel="C_DEBUG",
        )

        # 디버그 채널에 로그가 전송됨
        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        assert len(debug_calls) >= 1

    @pytest.mark.asyncio
    async def test_thread_buffers_passed_to_judge(self, store, channel_id):
        """스레드 버퍼가 judge에 전달되는지 확인"""
        _fill_pending(store, channel_id)
        store.append_thread_message(channel_id, "ts_a", {
            "ts": "9001.000", "user": "U99", "text": "스레드 대화 내용",
        })
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=999999,
        )

        assert observer.judge_call_count == 1
        assert "thread_buffers" in observer.judge_kwargs
        thread_buffers = observer.judge_kwargs["thread_buffers"]
        assert "ts_a" in thread_buffers
        assert thread_buffers["ts_a"][0]["text"] == "스레드 대화 내용"

    @pytest.mark.asyncio
    async def test_thread_buffers_cleared_after_pipeline(self, store, channel_id):
        """파이프라인 실행 후 스레드 버퍼도 judged로 이동되고 비워짐"""
        _fill_pending(store, channel_id, n=5)
        store.append_thread_message(channel_id, "ts_a", {
            "ts": "9001.000", "user": "U99", "text": "스레드 메시지",
        })
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            threshold_b=999999,
        )

        # 스레드 버퍼는 비어야 함
        assert store.load_all_thread_buffers(channel_id) == {}
        # pending + 스레드가 모두 judged로 이동
        judged = store.load_judged(channel_id)
        assert len(judged) == 6  # 5 pending + 1 thread

    @pytest.mark.asyncio
    async def test_existing_digest_passed_to_judge(self, store, channel_id):
        """기존 digest가 judge에 전달되는지 확인"""
        store.save_digest(channel_id, "이전 digest", {"token_count": 50})
        _fill_pending(store, channel_id)
        observer = FakeObserver()
        client = MagicMock()
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=300)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
        )

        assert observer.judge_call_count == 1


# ── 개입 모드 프롬프트 테스트 ──────────────────────────

class TestInterventionModePrompt:
    """개입 모드 프롬프트 빌더 테스트"""

    def test_system_prompt_exists(self):
        """개입 모드 시스템 프롬프트가 존재"""
        prompt = get_intervention_mode_system_prompt()
        assert prompt
        assert "서소영" in prompt

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

        store.append_pending("C123", {
            "ts": "1.1", "user": "U1", "text": "테스트 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
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

        store.append_pending("C123", {
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
        store.append_pending("C123", {
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

        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        system_prompt = call_args[1].get("system_prompt") or call_args[0][0]
        user_prompt = call_args[1].get("user_prompt") or call_args[0][1]

        assert "서소영" in system_prompt
        assert "기존 다이제스트" in user_prompt
        assert "새 메시지" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_buffer_skips(self, tmp_path):
        """pending 버퍼가 비어있으면 반응 스킵"""
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

        mock_llm.assert_not_called()
        client.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_clears_buffer_after_response(self, tmp_path):
        """반응 후 pending 버퍼를 비움"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=5)

        store.append_pending("C123", {
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

        assert len(store.load_pending("C123")) == 0

    @pytest.mark.asyncio
    async def test_debug_log_sent_on_respond(self, tmp_path):
        """개입 반응 시 디버그 채널에 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        store.append_pending("C123", {
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

        store.append_pending("C123", {
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

        store.append_pending("C123", {
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


# ── ClaudeAgentRunner Mock ────────────────────────────

@dataclass
class FakeClaudeResult:
    """ClaudeResult mock"""
    success: bool = True
    output: str = ""
    session_id: Optional[str] = None
    error: Optional[str] = None


class FakeClaudeRunner:
    """ClaudeAgentRunner mock for testing"""

    def __init__(self, output: str = "테스트 응답", success: bool = True, error: str = None):
        self._output = output
        self._success = success
        self._error = error
        self.run_call_count = 0
        self.last_prompt = None

    async def run(self, prompt: str, **kwargs) -> FakeClaudeResult:
        self.run_call_count += 1
        self.last_prompt = prompt
        return FakeClaudeResult(
            success=self._success,
            output=self._output if self._success else "",
            error=self._error,
        )


# ── Claude Runner 경로 테스트 ────────────────────────────

class TestIntervenWithClaudeRunner:
    """Claude Code SDK (claude_runner) 경로 테스트"""

    @pytest.mark.asyncio
    async def test_intervene_with_claude_runner(self, store, channel_id):
        """claude_runner가 있으면 Claude SDK로 응답 생성"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="1005.000",
            reaction_content="대화에 참여하고 싶습니다",
        ))
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=0)
        runner = FakeClaudeRunner(output="Claude SDK 응답입니다.")

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            claude_runner=runner,
        )

        # Claude runner가 호출됨
        assert runner.run_call_count == 1
        # 프롬프트에 system+user가 합쳐져 있어야 함
        assert runner.last_prompt is not None
        # 슬랙에 발송됨
        client.chat_postMessage.assert_called()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "Claude SDK 응답입니다" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_claude_runner_takes_priority_over_llm_call(self, store, channel_id):
        """claude_runner와 llm_call 모두 있으면 claude_runner가 우선"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입",
        ))
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=0)
        runner = FakeClaudeRunner(output="Claude 응답")
        mock_llm = AsyncMock(return_value="LLM 응답")

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            llm_call=mock_llm,
            claude_runner=runner,
        )

        # Claude runner가 호출됨
        assert runner.run_call_count == 1
        # llm_call은 호출되지 않음
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_claude_runner_failure_no_message_sent(self, store, channel_id):
        """Claude runner 실패 시 메시지 발송 안 됨"""
        _fill_pending(store, channel_id)
        observer = FakeObserver(judge_result=JudgeResult(
            importance=8,
            reaction_type="intervene",
            reaction_target="channel",
            reaction_content="개입",
        ))
        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        cooldown = CooldownManager(base_dir=store.base_dir, cooldown_sec=0)
        runner = FakeClaudeRunner(success=False, error="타임아웃")

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=cooldown,
            threshold_a=1,
            claude_runner=runner,
        )

        # 채널에 메시지 발송 안 됨 (디버그 채널이 아닌)
        calls = [c for c in client.chat_postMessage.call_args_list
                 if c[1].get("channel") == channel_id]
        assert len(calls) == 0


class TestRespondInInterventionModeWithClaudeRunner:
    """개입 모드 Claude Code SDK 경로 테스트"""

    @pytest.mark.asyncio
    async def test_responds_with_claude_runner(self, tmp_path):
        """claude_runner로 개입 모드 반응 생성"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        store.append_pending("C123", {
            "ts": "1.1", "user": "U1", "text": "테스트 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        runner = FakeClaudeRunner(output="Claude 개입 모드 응답")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            claude_runner=runner,
        )

        # Claude runner가 호출됨
        assert runner.run_call_count == 1
        # 슬랙에 메시지 발송됨
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "Claude 개입 모드 응답" in call_kwargs["text"]
        # 턴이 소모됨
        assert cooldown.get_remaining_turns("C123") == 2

    @pytest.mark.asyncio
    async def test_claude_runner_prompt_includes_context(self, tmp_path):
        """claude_runner 프롬프트에 system+user가 모두 포함"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=5)

        store.save_digest("C123", "채널 다이제스트 내용", {"token_count": 100})
        store.append_pending("C123", {
            "ts": "1.1", "user": "U1", "text": "새 메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        runner = FakeClaudeRunner(output="응답")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            claude_runner=runner,
        )

        assert runner.run_call_count == 1
        # 프롬프트에 system prompt (서소영) + user prompt (다이제스트, 메시지) 모두 포함
        prompt = runner.last_prompt
        assert "서소영" in prompt
        assert "채널 다이제스트 내용" in prompt
        assert "새 메시지" in prompt

    @pytest.mark.asyncio
    async def test_claude_runner_failure_sends_debug_log(self, tmp_path):
        """Claude runner 실패 시 디버그 로그 전송"""
        store = ChannelStore(base_dir=tmp_path)
        cooldown = CooldownManager(base_dir=tmp_path, cooldown_sec=300)
        cooldown.enter_intervention_mode("C123", max_turns=3)

        store.append_pending("C123", {
            "ts": "1.1", "user": "U1", "text": "메시지",
        })

        client = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ok": True})
        runner = FakeClaudeRunner(success=False, error="CLI 프로세스 오류")

        await respond_in_intervention_mode(
            store=store,
            channel_id="C123",
            slack_client=client,
            cooldown=cooldown,
            claude_runner=runner,
            debug_channel="C_DEBUG",
        )

        calls = client.chat_postMessage.call_args_list
        debug_calls = [c for c in calls if c[1].get("channel") == "C_DEBUG"]
        assert len(debug_calls) >= 1
        assert "오류" in debug_calls[0][1]["text"]
