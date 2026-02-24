"""Observer 모듈 단위 테스트"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.observer import (
    Observer,
    ObserverResult,
    parse_observer_output,
)
from seosoyoung.memory.prompts import (
    build_observer_system_prompt,
    build_observer_user_prompt,
)


class TestParseObserverOutput:
    def test_parse_full_output(self):
        text = json.dumps({
            "observations": [
                {"priority": "🔴", "content": "Critical finding", "session_date": "2026-02-10"},
                {"priority": "🟡", "content": "Medium priority note", "session_date": "2026-02-10"},
            ],
            "current_task": "Implementing Observational Memory",
            "suggested_response": "Remember to ask about OM progress",
            "candidates": [],
        })

        result = parse_observer_output(text)
        assert isinstance(result, ObserverResult)
        assert len(result.observations) == 2
        assert result.observations[0]["content"] == "Critical finding"
        assert result.observations[1]["content"] == "Medium priority note"
        assert result.current_task == "Implementing Observational Memory"
        assert result.suggested_response == "Remember to ask about OM progress"
        assert result.candidates == []

    def test_parse_with_candidates(self):
        text = json.dumps({
            "observations": [
                {"priority": "🔴", "content": "Critical finding", "session_date": "2026-02-10"},
            ],
            "current_task": "Working on memory system",
            "candidates": [
                {"priority": "🔴", "content": "사용자는 커밋 메시지를 항상 한국어로 작성하는 것을 선호한다"},
                {"priority": "🟡", "content": "트렐로 카드 작업 시 체크리스트를 먼저 확인한 후 작업을 시작하는 패턴"},
            ],
        })

        result = parse_observer_output(text)
        assert len(result.candidates) == 2
        assert "커밋 메시지를 항상 한국어로" in result.candidates[0]["content"]
        assert "체크리스트를 먼저 확인" in result.candidates[1]["content"]
        assert len(result.observations) == 1

    def test_parse_observations_only(self):
        text = json.dumps({
            "observations": [
                {"priority": "🔴", "content": "Only observations present", "session_date": "2026-02-10"},
            ],
        })

        result = parse_observer_output(text)
        assert len(result.observations) == 1
        assert result.observations[0]["content"] == "Only observations present"
        assert result.current_task == ""
        assert result.suggested_response == ""
        assert result.candidates == []

    def test_fallback_no_json(self):
        """JSON이 아닌 텍스트면 빈 결과"""
        text = "This is a plain text response without any JSON."
        result = parse_observer_output(text)
        assert result.observations == []

    def test_empty_input(self):
        result = parse_observer_output("")
        assert result.observations == []

    def test_parse_json_in_code_block(self):
        """```json 블록 안에 있는 JSON 파싱"""
        text = '```json\n{"observations": [{"priority": "🔴", "content": "Test", "session_date": "2026-02-10"}]}\n```'
        result = parse_observer_output(text)
        assert len(result.observations) == 1
        assert result.observations[0]["content"] == "Test"

    def test_preserves_existing_ids(self):
        """기존 항목과 동일한 content+priority면 기존 ID 유지"""
        existing = [
            {"id": "obs_20260210_000", "priority": "🔴", "content": "기존 관찰",
             "session_date": "2026-02-10", "created_at": "2026-02-10T00:00:00+00:00", "source": "observer"}
        ]
        text = json.dumps({
            "observations": [
                {"priority": "🔴", "content": "기존 관찰", "session_date": "2026-02-10"},
                {"priority": "🟡", "content": "새 관찰", "session_date": "2026-02-10"},
            ],
        })

        result = parse_observer_output(text, existing_items=existing)
        assert result.observations[0]["id"] == "obs_20260210_000"
        assert result.observations[1]["id"].startswith("obs_")


class TestObserverPrompts:
    def test_system_prompt_not_empty(self):
        prompt = build_observer_system_prompt()
        assert len(prompt) > 100
        assert "서소영" in prompt

    def test_system_prompt_includes_candidates_section(self):
        prompt = build_observer_system_prompt()
        assert "LONG-TERM MEMORY CANDIDATES" in prompt
        assert "candidates" in prompt

    def test_user_prompt_with_existing_observations(self):
        existing = [
            {"id": "obs_20260210_000", "priority": "🔴", "content": "Previous observation",
             "session_date": "2026-02-10", "created_at": "2026-02-10T00:00:00+00:00", "source": "observer"}
        ]
        prompt = build_observer_user_prompt(
            existing_observations=existing,
            messages=[
                {"role": "user", "content": "캐릭터 설정 수정해줘"},
                {"role": "assistant", "content": "수정했습니다."},
            ],
            current_time=datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc),
        )
        assert "EXISTING OBSERVATIONS" in prompt
        assert "Previous observation" in prompt
        assert "캐릭터 설정 수정해줘" in prompt
        assert "2026-02-10 09:30 UTC" in prompt

    def test_user_prompt_without_existing_observations(self):
        prompt = build_observer_user_prompt(
            existing_observations=None,
            messages=[{"role": "user", "content": "hello"}],
        )
        assert "first observation" in prompt

    def test_user_prompt_with_empty_observations(self):
        prompt = build_observer_user_prompt(
            existing_observations=[],
            messages=[{"role": "user", "content": "hello"}],
        )
        assert "first observation" in prompt


class TestObserverObserve:
    @pytest.fixture
    def observer(self):
        return Observer(api_key="test-key", model="gpt-4.1-mini")

    @pytest.fixture
    def sample_messages(self):
        return [
            {"role": "user", "content": "이번에 eb_lore의 캐릭터 설정을 대폭 수정하려고 합니다."},
            {"role": "assistant", "content": "네, 어떤 캐릭터를 수정하실 건가요?"},
        ]

    @pytest.mark.asyncio
    async def test_observe_calls_api(self, observer, sample_messages):
        """API를 호출하여 관찰 결과를 반환"""
        api_response = json.dumps({
            "observations": [
                {"priority": "🔴", "content": "Test observation", "session_date": "2026-02-10"},
            ],
        })
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=api_response))
        ]

        observer.client = AsyncMock()
        observer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await observer.observe(None, sample_messages)

        assert result is not None
        assert len(result.observations) == 1
        assert result.observations[0]["content"] == "Test observation"
        observer.client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_observe_raises_on_api_error(self, observer, sample_messages):
        """API 오류 시 예외가 전파됨 (파이프라인에서 처리)"""
        observer.client = AsyncMock()
        observer.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        with pytest.raises(Exception, match="API Error"):
            await observer.observe(None, sample_messages)

    @pytest.mark.asyncio
    async def test_observe_with_existing_observations(self, observer, sample_messages):
        """기존 관찰이 있을 때 API에 전달되는지 확인"""
        existing = [
            {"id": "obs_20260210_000", "priority": "🔴", "content": "Previous observation",
             "session_date": "2026-02-10", "created_at": "2026-02-10T00:00:00+00:00", "source": "observer"}
        ]
        api_response = json.dumps({
            "observations": [
                {"id": "obs_20260210_000", "priority": "🔴", "content": "Previous observation", "session_date": "2026-02-10"},
                {"priority": "🟡", "content": "Updated observation", "session_date": "2026-02-10"},
            ],
        })
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=api_response))
        ]

        observer.client = AsyncMock()
        observer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await observer.observe(existing, sample_messages)

        assert result is not None
        # API 호출 시 기존 관찰이 포함되었는지 확인
        call_args = observer.client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Previous observation" in user_msg
