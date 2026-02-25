"""
test_engine_adapter - SoulEngineAdapter 유닛 테스트

ClaudeRunner.run()을 모킹하여 Queue 기반 스트리밍 변환을 검증합니다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.soul.models import (
    CompactEvent,
    CompleteEvent,
    ContextUsageEvent,
    ErrorEvent,
    InterventionSentEvent,
    ProgressEvent,
)
from seosoyoung.soul.service.engine_adapter import (
    SoulEngineAdapter,
    _build_intervention_prompt,
    _extract_context_usage,
    InterventionMessage,
)
from seosoyoung.slackbot.claude.engine_types import EngineResult


# === Helper: collect all events from async generator ===

async def collect_events(adapter, prompt, **kwargs) -> list:
    events = []
    async for event in adapter.execute(prompt, **kwargs):
        events.append(event)
    return events


# === _extract_context_usage ===

class TestExtractContextUsage:
    def test_none_usage(self):
        assert _extract_context_usage(None) is None

    def test_empty_usage(self):
        assert _extract_context_usage({}) is None

    def test_zero_tokens(self):
        assert _extract_context_usage({"input_tokens": 0, "output_tokens": 0}) is None

    def test_valid_usage(self):
        event = _extract_context_usage({
            "input_tokens": 50000,
            "output_tokens": 10000,
        })
        assert event is not None
        assert isinstance(event, ContextUsageEvent)
        assert event.used_tokens == 60000
        assert event.max_tokens == 200_000
        assert event.percent == 30.0


# === _build_intervention_prompt ===

class TestBuildInterventionPrompt:
    def test_without_attachments(self):
        msg = InterventionMessage(text="hello", user="alice", attachment_paths=[])
        prompt = _build_intervention_prompt(msg)
        assert "alice" in prompt
        assert "hello" in prompt
        assert "첨부" not in prompt

    def test_with_attachments(self):
        msg = InterventionMessage(
            text="check this",
            user="bob",
            attachment_paths=["/tmp/a.txt", "/tmp/b.png"],
        )
        prompt = _build_intervention_prompt(msg)
        assert "bob" in prompt
        assert "check this" in prompt
        assert "/tmp/a.txt" in prompt
        assert "/tmp/b.png" in prompt
        assert "첨부 파일" in prompt


# === SoulEngineAdapter ===

class TestSoulEngineAdapterSuccess:
    """정상 실행 시나리오"""

    async def test_complete_event_on_success(self):
        """성공적인 실행 → CompleteEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(
            success=True,
            output="작업 완료",
            session_id="sess-123",
        )

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "do something")

        assert len(events) == 1
        assert isinstance(events[0], CompleteEvent)
        assert events[0].result == "작업 완료"
        assert events[0].claude_session_id == "sess-123"

    async def test_complete_with_usage(self):
        """usage가 있으면 ContextUsageEvent → CompleteEvent 순서"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(
            success=True,
            output="done",
            session_id="sess-456",
            usage={"input_tokens": 100000, "output_tokens": 50000},
        )

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "work")

        assert len(events) == 2
        assert isinstance(events[0], ContextUsageEvent)
        assert events[0].used_tokens == 150000
        assert isinstance(events[1], CompleteEvent)

    async def test_empty_output_fallback(self):
        """빈 output → '(결과 없음)' fallback"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        assert len(events) == 1
        assert isinstance(events[0], CompleteEvent)
        assert events[0].result == "(결과 없음)"


class TestSoulEngineAdapterError:
    """에러 시나리오"""

    async def test_error_event_on_failure(self):
        """실패한 실행 → ErrorEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(
            success=False,
            output="",
            error="SDK not available",
        )

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "SDK not available" in events[0].message

    async def test_error_event_on_is_error(self):
        """is_error=True → ErrorEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(
            success=True,
            output="error output",
            is_error=True,
            error="something wrong",
        )

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)

    async def test_error_event_on_exception(self):
        """예외 발생 → ErrorEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("boom"))

            events = await collect_events(adapter, "test")

        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "boom" in events[0].message


class TestSoulEngineAdapterCallbacks:
    """콜백 → 이벤트 변환 테스트"""

    async def test_progress_callback_yields_event(self):
        """on_progress 콜백 → ProgressEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None):
            if on_progress:
                await on_progress("진행 중...")
                await on_progress("거의 완료...")
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run

            events = await collect_events(adapter, "work")

        progress_events = [e for e in events if isinstance(e, ProgressEvent)]
        assert len(progress_events) == 2
        assert progress_events[0].text == "진행 중..."
        assert progress_events[1].text == "거의 완료..."

    async def test_compact_callback_yields_event(self):
        """on_compact 콜백 → CompactEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None):
            if on_compact:
                await on_compact("auto", "컨텍스트 컴팩트 실행됨")
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run

            events = await collect_events(adapter, "work")

        compact_events = [e for e in events if isinstance(e, CompactEvent)]
        assert len(compact_events) == 1
        assert compact_events[0].trigger == "auto"

    async def test_intervention_callback(self):
        """intervention 콜백 → InterventionSentEvent + prompt 반환"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        intervention_prompts = []

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None):
            if on_intervention:
                result = await on_intervention()
                if result:
                    intervention_prompts.append(result)
            return EngineResult(success=True, output="done")

        call_count = 0

        async def get_intervention():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "text": "추가 지시",
                    "user": "alice",
                    "attachment_paths": [],
                }
            return None

        on_sent = AsyncMock()

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run

            events = await collect_events(
                adapter, "work",
                get_intervention=get_intervention,
                on_intervention_sent=on_sent,
            )

        # InterventionSentEvent가 큐를 통해 발행되었는지
        intervention_events = [
            e for e in events if isinstance(e, InterventionSentEvent)
        ]
        assert len(intervention_events) == 1
        assert intervention_events[0].user == "alice"
        assert intervention_events[0].text == "추가 지시"

        # on_intervention_sent 콜백 호출 확인
        on_sent.assert_awaited_once_with("alice", "추가 지시")

        # 반환된 프롬프트에 개입 메시지가 포함
        assert len(intervention_prompts) == 1
        assert "alice" in intervention_prompts[0]
        assert "추가 지시" in intervention_prompts[0]

    async def test_intervention_with_attachments(self):
        """첨부 파일이 있는 intervention"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        intervention_prompts = []

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None):
            if on_intervention:
                result = await on_intervention()
                if result:
                    intervention_prompts.append(result)
            return EngineResult(success=True, output="done")

        async def get_intervention():
            return {
                "text": "파일 확인",
                "user": "bob",
                "attachment_paths": ["/tmp/doc.pdf"],
            }

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run

            events = await collect_events(
                adapter, "work",
                get_intervention=get_intervention,
            )

        assert len(intervention_prompts) == 1
        assert "/tmp/doc.pdf" in intervention_prompts[0]
        assert "첨부 파일" in intervention_prompts[0]


class TestSoulEngineAdapterResumeSession:
    """세션 resume 테스트"""

    async def test_resume_session_id_passed(self):
        """resume_session_id가 ClaudeRunner.run()에 전달됨"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="resumed")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "continue",
                resume_session_id="prev-session-123",
            )

        instance.run.assert_awaited_once()
        call_kwargs = instance.run.call_args
        assert call_kwargs.kwargs.get("session_id") == "prev-session-123"


class TestSoulEngineAdapterToolSettings:
    """요청별 도구 설정 전달 테스트"""

    async def test_default_tools_when_none(self):
        """allowed_tools/disallowed_tools가 None이면 기본값 사용"""
        from seosoyoung.soul.service.engine_adapter import (
            DEFAULT_ALLOWED_TOOLS,
            DEFAULT_DISALLOWED_TOOLS,
        )
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        # ClaudeRunner가 기본 도구 설정으로 생성되었는지 확인
        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["allowed_tools"] == DEFAULT_ALLOWED_TOOLS
        assert call_kwargs["disallowed_tools"] == DEFAULT_DISALLOWED_TOOLS

    async def test_custom_allowed_tools_passed(self):
        """allowed_tools가 지정되면 ClaudeRunner에 전달됨"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")
        custom_tools = ["Read", "Glob"]

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "test",
                allowed_tools=custom_tools,
            )

        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["allowed_tools"] == custom_tools

    async def test_custom_disallowed_tools_passed(self):
        """disallowed_tools가 지정되면 ClaudeRunner에 전달됨"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")
        custom_disallowed = ["Bash", "Write", "Edit"]

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "test",
                disallowed_tools=custom_disallowed,
            )

        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["disallowed_tools"] == custom_disallowed

    async def test_use_mcp_false_no_mcp_config(self):
        """use_mcp=False이면 mcp_config_path=None"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "test",
                use_mcp=False,
            )

        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["mcp_config_path"] is None

    async def test_use_mcp_true_resolves_config(self, tmp_path):
        """use_mcp=True이면 workspace_dir/mcp_config.json을 해석"""
        # mcp_config.json 생성
        config_path = tmp_path / "mcp_config.json"
        config_path.write_text('{"mcpServers": {}}')

        adapter = SoulEngineAdapter(workspace_dir=str(tmp_path))
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "test",
                use_mcp=True,
            )

        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["mcp_config_path"] == config_path

    async def test_use_mcp_true_no_config_file(self):
        """use_mcp=True이지만 파일이 없으면 mcp_config_path=None"""
        adapter = SoulEngineAdapter(workspace_dir="/nonexistent/path")
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(
                adapter, "test",
                use_mcp=True,
            )

        call_kwargs = MockRunner.call_args.kwargs
        assert call_kwargs["mcp_config_path"] is None
