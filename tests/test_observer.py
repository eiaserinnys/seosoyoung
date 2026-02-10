"""Observer 모듈 단위 테스트"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.observer import (
    Observer,
    ObserverResult,
    parse_observer_output,
    _extract_tag,
)
from seosoyoung.memory.prompts import (
    build_observer_system_prompt,
    build_observer_user_prompt,
)


class TestExtractTag:
    def test_extract_existing_tag(self):
        text = "<observations>some observations here</observations>"
        assert _extract_tag(text, "observations") == "some observations here"

    def test_extract_missing_tag(self):
        text = "no tags here"
        assert _extract_tag(text, "observations") == ""

    def test_extract_multiline_tag(self):
        text = """<observations>
## [2026-02-10] Session Observations

🔴 User prefers Korean commit messages
🟡 Working on eb_lore updates
</observations>"""
        result = _extract_tag(text, "observations")
        assert "🔴 User prefers Korean commit messages" in result
        assert "🟡 Working on eb_lore updates" in result

    def test_extract_current_task(self):
        text = "<current-task>Working on memory system</current-task>"
        assert _extract_tag(text, "current-task") == "Working on memory system"

    def test_extract_suggested_response(self):
        text = "<suggested-response>Mention the OM progress</suggested-response>"
        assert _extract_tag(text, "suggested-response") == "Mention the OM progress"


class TestParseObserverOutput:
    def test_parse_full_output(self):
        text = """<observations>
## [2026-02-10] Session Observations

🔴 Critical finding
🟡 Medium priority note
</observations>

<current-task>
Implementing Observational Memory
</current-task>

<suggested-response>
Remember to ask about OM progress
</suggested-response>"""

        result = parse_observer_output(text)
        assert isinstance(result, ObserverResult)
        assert "🔴 Critical finding" in result.observations
        assert "Implementing Observational Memory" in result.current_task
        assert "Remember to ask about OM progress" in result.suggested_response

    def test_parse_observations_only(self):
        text = """<observations>
🔴 Only observations present
</observations>"""

        result = parse_observer_output(text)
        assert "🔴 Only observations present" in result.observations
        assert result.current_task == ""
        assert result.suggested_response == ""

    def test_fallback_no_tags(self):
        """태그가 없으면 전체 텍스트를 observations로 사용"""
        text = "This is a plain text response without any XML tags."
        result = parse_observer_output(text)
        assert result.observations == text

    def test_empty_input(self):
        result = parse_observer_output("")
        assert result.observations == ""


class TestObserverPrompts:
    def test_system_prompt_not_empty(self):
        prompt = build_observer_system_prompt()
        assert len(prompt) > 100
        assert "서소영" in prompt

    def test_user_prompt_with_existing_observations(self):
        prompt = build_observer_user_prompt(
            existing_observations="🔴 Previous observation",
            messages=[
                {"role": "user", "content": "캐릭터 설정 수정해줘"},
                {"role": "assistant", "content": "수정했습니다."},
            ],
            current_time=datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc),
        )
        assert "EXISTING OBSERVATIONS" in prompt
        assert "🔴 Previous observation" in prompt
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
            existing_observations="",
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
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="<observations>\n🔴 Test observation\n</observations>"
                )
            )
        ]

        observer.client = AsyncMock()
        observer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await observer.observe(None, sample_messages)

        assert result is not None
        assert "🔴 Test observation" in result.observations
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
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="<observations>\n🔴 Updated observation\n</observations>"
                )
            )
        ]

        observer.client = AsyncMock()
        observer.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await observer.observe(
            "🔴 Previous observation",
            sample_messages,
        )

        assert result is not None
        # API 호출 시 기존 관찰이 포함되었는지 확인
        call_args = observer.client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert "Previous observation" in user_msg
