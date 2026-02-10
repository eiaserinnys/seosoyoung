"""관찰 파이프라인 테스트"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.observation_pipeline import observe_conversation
from seosoyoung.memory.observer import ObserverResult
from seosoyoung.memory.store import MemoryRecord, MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(base_dir=tmp_path)


@pytest.fixture
def mock_observer():
    observer = AsyncMock()
    observer.observe = AsyncMock()
    return observer


@pytest.fixture
def sample_messages():
    return [
        {"role": "user", "content": "안녕하세요, 캐릭터 정보 찾아줘"},
        {"role": "assistant", "content": "네, 찾아보겠습니다."},
        {"role": "assistant", "content": "펜릭스는 마법검사입니다."},
    ]


class TestObserveConversation:
    @pytest.mark.asyncio
    async def test_first_observation_creates_record(
        self, store, mock_observer, sample_messages
    ):
        """첫 관찰 시 새 레코드를 생성"""
        mock_observer.observe.return_value = ObserverResult(
            observations="## [2026-02-10] Session Observations\n\n🔴 사용자가 캐릭터 정보를 요청함",
            current_task="캐릭터 정보 조회",
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=0,
        )

        assert result is True
        record = store.get_record("U12345")
        assert record is not None
        assert "캐릭터 정보를 요청함" in record.observations
        assert record.total_sessions_observed == 1
        assert record.last_observed_at is not None
        assert record.observation_tokens > 0

    @pytest.mark.asyncio
    async def test_subsequent_observation_updates_record(
        self, store, mock_observer, sample_messages
    ):
        """기존 레코드가 있을 때 갱신"""
        # 기존 레코드 생성
        existing_record = MemoryRecord(
            user_id="U12345",
            observations="## [2026-02-09] Previous\n\n🔴 이전 관찰",
            observation_tokens=50,
            total_sessions_observed=1,
        )
        store.save_record(existing_record)

        mock_observer.observe.return_value = ObserverResult(
            observations="## [2026-02-10] Updated\n\n🔴 갱신된 관찰\n\n## [2026-02-09] Previous\n\n🔴 이전 관찰",
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=0,
        )

        assert result is True
        record = store.get_record("U12345")
        assert record.total_sessions_observed == 2
        assert "갱신된 관찰" in record.observations
        # Observer에 기존 관찰 로그가 전달되었는지 확인
        mock_observer.observe.assert_called_once()
        call_args = mock_observer.observe.call_args
        assert "이전 관찰" in call_args.kwargs["existing_observations"]

    @pytest.mark.asyncio
    async def test_short_conversation_skipped(
        self, store, mock_observer, sample_messages
    ):
        """Observer가 None을 반환하면 건너뜀"""
        mock_observer.observe.return_value = None

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=500,
        )

        assert result is False
        assert store.get_record("U12345") is None

    @pytest.mark.asyncio
    async def test_observer_error_returns_false(
        self, store, mock_observer, sample_messages
    ):
        """Observer 오류 시 False 반환 (에러 전파 없음)"""
        mock_observer.observe.side_effect = Exception("API 오류")

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_passes_existing_observations_to_observer(
        self, store, mock_observer, sample_messages
    ):
        """기존 관찰 로그를 Observer에 전달"""
        existing = MemoryRecord(
            user_id="U12345",
            observations="기존 관찰 내용",
        )
        store.save_record(existing)

        mock_observer.observe.return_value = ObserverResult(
            observations="갱신된 관찰",
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=0,
        )

        call_kwargs = mock_observer.observe.call_args.kwargs
        assert call_kwargs["existing_observations"] == "기존 관찰 내용"
        assert call_kwargs["messages"] == sample_messages

    @pytest.mark.asyncio
    async def test_no_existing_record_passes_none(
        self, store, mock_observer, sample_messages
    ):
        """기존 레코드 없을 때 None 전달"""
        mock_observer.observe.return_value = ObserverResult(observations="새 관찰")

        await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=0,
        )

        call_kwargs = mock_observer.observe.call_args.kwargs
        assert call_kwargs["existing_observations"] is None

    @pytest.mark.asyncio
    async def test_token_count_updated(
        self, store, mock_observer, sample_messages
    ):
        """관찰 후 토큰 수가 올바르게 갱신됨"""
        long_observations = "관찰 내용 " * 100
        mock_observer.observe.return_value = ObserverResult(
            observations=long_observations,
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            user_id="U12345",
            messages=sample_messages,
            min_conversation_tokens=0,
        )

        record = store.get_record("U12345")
        assert record.observation_tokens > 0


class TestTriggerObservation:
    """agent_runner._trigger_observation 테스트"""

    @pytest.mark.asyncio
    async def test_trigger_creates_thread(self):
        """_trigger_observation이 별도 스레드를 생성하는지 확인"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()
        messages = [{"role": "assistant", "content": "응답"}]

        with patch("seosoyoung.claude.agent_runner.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            with patch("seosoyoung.config.Config.OM_ENABLED", True):
                runner._trigger_observation("U12345", "프롬프트", messages)

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_disabled_when_om_off(self):
        """OM이 비활성화되면 트리거하지 않음"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.claude.agent_runner.threading.Thread") as mock_thread:
            with patch("seosoyoung.config.Config.OM_ENABLED", False):
                runner._trigger_observation("U12345", "프롬프트", [])

        mock_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_error_does_not_propagate(self):
        """트리거 오류가 전파되지 않음"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        with patch(
            "seosoyoung.config.Config.OM_ENABLED",
            new_callable=lambda: property(lambda self: (_ for _ in ()).throw(RuntimeError("설정 오류"))),
        ):
            # Config import 자체가 실패해도 에러 전파 없음
            runner._trigger_observation("U12345", "프롬프트", [])

    @pytest.mark.asyncio
    async def test_trigger_prepends_user_message(self):
        """트리거 시 사용자 메시지가 앞에 추가되는지 확인"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()
        collected = [{"role": "assistant", "content": "응답"}]
        captured_messages = []

        async def mock_observe(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return False

        # Thread.start()를 가로채서 target을 직접 실행
        def run_thread_target_directly(target, daemon=True):
            mock_t = MagicMock()
            mock_t.start = lambda: target()
            return mock_t

        with patch("seosoyoung.config.Config.OM_ENABLED", True):
            with patch("seosoyoung.config.Config.OPENAI_API_KEY", "test-key"):
                with patch("seosoyoung.config.Config.OM_MODEL", "gpt-4.1-mini"):
                    with patch("seosoyoung.config.Config.get_memory_path", return_value="/tmp/test"):
                        with patch("seosoyoung.config.Config.OM_MIN_CONVERSATION_TOKENS", 0):
                            with patch(
                                "seosoyoung.memory.observation_pipeline.observe_conversation",
                                side_effect=mock_observe,
                            ) as mock_obs:
                                with patch(
                                    "seosoyoung.claude.agent_runner.threading.Thread",
                                    side_effect=run_thread_target_directly,
                                ):
                                    runner._trigger_observation("U12345", "테스트 프롬프트", collected)

        mock_obs.assert_called_once()
        call_kwargs = mock_obs.call_args.kwargs
        assert call_kwargs["messages"][0] == {"role": "user", "content": "테스트 프롬프트"}
        assert call_kwargs["messages"][1] == {"role": "assistant", "content": "응답"}


class TestRunTriggersObservation:
    """run() 메서드에서 관찰이 트리거되는지 통합 테스트"""

    @pytest.mark.asyncio
    async def test_run_triggers_observation_on_success(self):
        """성공적인 실행 후 관찰이 트리거됨"""
        from dataclasses import dataclass
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        @dataclass
        class MockResultMessage:
            result: str
            session_id: str = None

        @dataclass
        class MockTextBlock:
            text: str

        @dataclass
        class MockAssistantMessage:
            content: list

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockAssistantMessage(content=[MockTextBlock(text="작업 중...")])
            yield MockResultMessage(result="완료", session_id="test")

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                        with patch.object(runner, "_trigger_observation") as mock_trigger:
                            result = await runner.run("테스트", user_id="U12345")

        assert result.success is True
        mock_trigger.assert_called_once_with(
            "U12345",
            "테스트",
            result.collected_messages,
        )

    @pytest.mark.asyncio
    async def test_run_does_not_trigger_without_user_id(self):
        """user_id 없으면 관찰을 트리거하지 않음"""
        from dataclasses import dataclass
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        @dataclass
        class MockResultMessage:
            result: str
            session_id: str = None

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(result="완료", session_id="test")

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_trigger_observation") as mock_trigger:
                    result = await runner.run("테스트")

        assert result.success is True
        mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_does_not_trigger_on_failure(self):
        """실행 실패 시 관찰을 트리거하지 않음"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            raise RuntimeError("실행 오류")
            yield

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch.object(runner, "_trigger_observation") as mock_trigger:
                result = await runner.run("테스트", user_id="U12345")

        assert result.success is False
        mock_trigger.assert_not_called()
