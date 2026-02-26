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
    DebugEvent,
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
from seosoyoung.soul.service.runner_pool import ClaudeRunnerPool
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
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
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
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
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
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
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
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
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


class TestSoulEngineAdapterDebugEvent:
    """debug_send_fn → DebugEvent 변환 테스트"""

    async def test_debug_send_fn_passed_to_runner(self):
        """ClaudeRunner 생성 시 debug_send_fn이 전달되는지 확인"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        call_kwargs = MockRunner.call_args.kwargs
        assert "debug_send_fn" in call_kwargs
        assert call_kwargs["debug_send_fn"] is not None
        assert callable(call_kwargs["debug_send_fn"])

    async def test_debug_send_fn_produces_event_in_stream(self):
        """debug_send_fn 호출이 실제로 DebugEvent를 스트림에 넣는지 확인"""
        adapter = SoulEngineAdapter(workspace_dir="/test")

        captured_debug_fn = None

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            # debug_send_fn을 동기적으로 호출 (ClaudeRunner._debug()와 동일한 패턴)
            if captured_debug_fn:
                captured_debug_fn("rate limit warning: 80% used")
                # 이벤트가 큐에 들어갈 시간을 줌
                await asyncio.sleep(0.01)
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            def capture_init(*args, **kwargs):
                nonlocal captured_debug_fn
                captured_debug_fn = kwargs.get("debug_send_fn")
                instance = MagicMock()
                instance.run = fake_run
                return instance

            MockRunner.side_effect = capture_init

            events = await collect_events(adapter, "test")

        debug_events = [e for e in events if isinstance(e, DebugEvent)]
        assert len(debug_events) == 1
        assert debug_events[0].message == "rate limit warning: 80% used"
        assert debug_events[0].type == "debug"

    async def test_multiple_debug_events(self):
        """여러 debug_send_fn 호출 → 여러 DebugEvent"""
        adapter = SoulEngineAdapter(workspace_dir="/test")

        captured_debug_fn = None

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if captured_debug_fn:
                captured_debug_fn("warning 1")
                captured_debug_fn("warning 2")
                await asyncio.sleep(0.01)
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            def capture_init(*args, **kwargs):
                nonlocal captured_debug_fn
                captured_debug_fn = kwargs.get("debug_send_fn")
                instance = MagicMock()
                instance.run = fake_run
                return instance

            MockRunner.side_effect = capture_init

            events = await collect_events(adapter, "test")

        debug_events = [e for e in events if isinstance(e, DebugEvent)]
        assert len(debug_events) == 2
        assert debug_events[0].message == "warning 1"
        assert debug_events[1].message == "warning 2"


# === ClaudeRunnerPool 통합 테스트 ===

class TestSoulEngineAdapterWithPool:
    """풀 주입 시나리오"""

    async def test_pool_none_creates_runner_directly(self):
        """pool=None이면 기존처럼 ClaudeRunner를 직접 생성"""
        adapter = SoulEngineAdapter(workspace_dir="/test")  # pool 없음
        mock_result = EngineResult(success=True, output="done", session_id="s1")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "test")

        # ClaudeRunner 직접 생성됨
        assert MockRunner.called
        assert isinstance(events[-1], CompleteEvent)

    async def test_pool_acquire_called_on_execute(self):
        """풀이 있으면 acquire()가 호출됨"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(success=True, output="done", session_id="sess-abc")
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test prompt")

        mock_pool.acquire.assert_awaited_once()

    async def test_pool_acquire_passes_resume_session_id(self):
        """resume_session_id가 pool.acquire()에 전달됨"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(success=True, output="done", session_id="sess-xyz")
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "continue", resume_session_id="sess-xyz")

        call_kwargs = mock_pool.acquire.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-xyz"

    async def test_pool_release_called_on_success(self):
        """성공 시 result.session_id로 release() 호출"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(success=True, output="done", session_id="sess-new")
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test")

        mock_pool.release.assert_awaited_once()
        call_kwargs = mock_pool.release.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-new"
        assert mock_pool.release.call_args.args[0] is mock_runner

    async def test_pool_not_released_on_error_result(self):
        """에러 결과(success=False) 시 release 호출 안 함 (runner 폐기)"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(
            success=False,
            output="",
            error="something failed",
        )
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test")

        # release 호출 안 됨
        mock_pool.release.assert_not_awaited()
        # ErrorEvent 발행됨
        assert any(isinstance(e, ErrorEvent) for e in events)

    async def test_pool_not_released_on_is_error(self):
        """is_error=True 시 release 호출 안 함"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(
            success=True,
            output="error output",
            is_error=True,
            error="engine error",
        )
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test")

        mock_pool.release.assert_not_awaited()

    async def test_pool_not_released_on_exception(self):
        """예외 발생 시 release 호출 안 함"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_runner.run = AsyncMock(side_effect=RuntimeError("runner crashed"))
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test")

        mock_pool.release.assert_not_awaited()
        assert any(isinstance(e, ErrorEvent) for e in events)

    async def test_pool_runner_not_created_via_clauderunner_constructor(self):
        """풀이 있으면 ClaudeRunner 생성자 직접 호출 안 함"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(success=True, output="done", session_id="s1")
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            events = await collect_events(adapter, "test")

        # 직접 생성자 호출 없음
        assert not MockRunner.called

    async def test_complete_event_contains_session_id_from_result(self):
        """CompleteEvent.claude_session_id = result.session_id"""
        mock_pool = MagicMock(spec=ClaudeRunnerPool)
        mock_runner = MagicMock()
        mock_result = EngineResult(success=True, output="result text", session_id="final-sess")
        mock_runner.run = AsyncMock(return_value=mock_result)
        mock_pool.acquire = AsyncMock(return_value=mock_runner)
        mock_pool.release = AsyncMock()

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=mock_pool)
        events = await collect_events(adapter, "test")

        complete = next(e for e in events if isinstance(e, CompleteEvent))
        assert complete.claude_session_id == "final-sess"


# === _CardTracker 유닛 테스트 ===

class TestCardTracker:
    """_CardTracker 유닛 테스트"""

    def test_initial_state(self):
        """초기 상태: card_id와 last_tool 모두 None"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        assert tracker.current_card_id is None
        assert tracker.last_tool is None

    def test_new_card_returns_string(self):
        """new_card()는 문자열 반환"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        card_id = tracker.new_card()
        assert isinstance(card_id, str)
        assert len(card_id) > 0

    def test_new_card_updates_current(self):
        """new_card() 후 current_card_id가 갱신됨"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        new_id = tracker.new_card()
        assert tracker.current_card_id == new_id

    def test_new_card_generates_unique_ids(self):
        """new_card() 연속 호출 → 서로 다른 ID 반환"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        ids = {tracker.new_card() for _ in range(10)}
        assert len(ids) == 10

    def test_set_last_tool(self):
        """set_last_tool 후 last_tool 반환"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        tracker.set_last_tool("Read")
        assert tracker.last_tool == "Read"
        tracker.set_last_tool("Grep")
        assert tracker.last_tool == "Grep"

    def test_current_card_id_overwritten_by_new_card(self):
        """new_card()를 두 번 호출하면 이전 card_id는 덮어써짐"""
        from seosoyoung.soul.service.engine_adapter import _CardTracker
        tracker = _CardTracker()
        id1 = tracker.new_card()
        id2 = tracker.new_card()
        assert id1 != id2
        assert tracker.current_card_id == id2


# === EngineEvent → SSE 이벤트 변환 테스트 ===

class TestEngineEventConversion:
    """on_engine_event 콜백 → SSE 이벤트 변환 테스트"""

    async def test_thinking_delta_produces_three_events(self):
        """THINKING_DELTA → ThinkingStart + ThinkingDelta + ThinkingEnd"""
        from seosoyoung.soul.models import (
            ThinkingDeltaSSEEvent,
            ThinkingEndSSEEvent,
            ThinkingStartSSEEvent,
        )
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.THINKING_DELTA,
                    data={"text": "모델이 생각 중..."},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        thinking_events = [
            e for e in events
            if isinstance(e, (ThinkingStartSSEEvent, ThinkingDeltaSSEEvent, ThinkingEndSSEEvent))
        ]
        assert len(thinking_events) == 3
        start, delta, end = thinking_events
        assert isinstance(start, ThinkingStartSSEEvent)
        assert isinstance(delta, ThinkingDeltaSSEEvent)
        assert isinstance(end, ThinkingEndSSEEvent)
        # 세 이벤트 모두 동일한 card_id
        assert start.card_id == delta.card_id == end.card_id
        assert delta.text == "모델이 생각 중..."

    async def test_tool_start_event(self):
        """TOOL_START → ToolStartSSEEvent"""
        from seosoyoung.soul.models import ToolStartSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.TOOL_START,
                    data={"tool_name": "Read", "tool_input": {"file_path": "/test.txt"}},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        tool_events = [e for e in events if isinstance(e, ToolStartSSEEvent)]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "Read"
        assert tool_events[0].tool_input == {"file_path": "/test.txt"}

    async def test_tool_result_event(self):
        """TOOL_RESULT → ToolResultSSEEvent"""
        from seosoyoung.soul.models import ToolResultSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.TOOL_RESULT,
                    data={"tool_name": "Bash", "result": "file content", "is_error": False},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        result_events = [e for e in events if isinstance(e, ToolResultSSEEvent)]
        assert len(result_events) == 1
        assert result_events[0].tool_name == "Bash"
        assert result_events[0].result == "file content"
        assert result_events[0].is_error is False

    async def test_engine_result_event(self):
        """RESULT → ResultSSEEvent"""
        from seosoyoung.soul.models import ResultSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.RESULT,
                    data={"success": True, "output": "최종 결과", "error": None},
                ))
            return EngineResult(success=True, output="최종 결과")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        result_events = [e for e in events if isinstance(e, ResultSSEEvent)]
        assert len(result_events) == 1
        assert result_events[0].success is True
        assert result_events[0].output == "최종 결과"

    async def test_multiple_thinking_blocks_get_distinct_card_ids(self):
        """두 THINKING_DELTA → 서로 다른 card_id"""
        from seosoyoung.soul.models import ThinkingStartSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.THINKING_DELTA,
                    data={"text": "첫 번째 사고"},
                ))
                await on_event(EngineEvent(
                    type=EngineEventType.THINKING_DELTA,
                    data={"text": "두 번째 사고"},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        start_events = [e for e in events if isinstance(e, ThinkingStartSSEEvent)]
        assert len(start_events) == 2
        assert start_events[0].card_id != start_events[1].card_id

    async def test_tool_linked_to_thinking_card(self):
        """TOOL_START.card_id = 직전 THINKING_DELTA의 card_id"""
        from seosoyoung.soul.models import ThinkingStartSSEEvent, ToolStartSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.THINKING_DELTA,
                    data={"text": "Read 파일을 먼저"},
                ))
                await on_event(EngineEvent(
                    type=EngineEventType.TOOL_START,
                    data={"tool_name": "Read", "tool_input": {}},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        thinking_starts = [e for e in events if isinstance(e, ThinkingStartSSEEvent)]
        tool_starts = [e for e in events if isinstance(e, ToolStartSSEEvent)]
        assert len(thinking_starts) == 1
        assert len(tool_starts) == 1
        assert thinking_starts[0].card_id == tool_starts[0].card_id

    async def test_existing_progress_still_emitted_alongside_new_events(self):
        """기존 ProgressEvent도 그대로 발행 (슬랙봇 하위호환)"""
        from seosoyoung.soul.models import ThinkingStartSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            # 기존 on_progress (슬랙봇용)
            if on_progress:
                await on_progress("작업 중...")
            # 신규 on_event (dashboard용)
            if on_event:
                await on_event(EngineEvent(
                    type=EngineEventType.THINKING_DELTA,
                    data={"text": "사고 중..."},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        # 기존 ProgressEvent 유지
        progress_events = [e for e in events if isinstance(e, ProgressEvent)]
        assert len(progress_events) == 1
        # 신규 ThinkingStartSSEEvent 추가
        thinking_events = [e for e in events if isinstance(e, ThinkingStartSSEEvent)]
        assert len(thinking_events) == 1

    async def test_on_event_passed_to_runner(self):
        """runner.run()에 on_event 키워드 인자가 전달됨"""
        adapter = SoulEngineAdapter(workspace_dir="/test")
        mock_result = EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)
            events = await collect_events(adapter, "test")

        call_kwargs = instance.run.call_args.kwargs
        assert "on_event" in call_kwargs
        assert call_kwargs["on_event"] is not None
        assert callable(call_kwargs["on_event"])

    async def test_tool_result_fallback_tool_name(self):
        """TOOL_RESULT에 tool_name 없으면 tracker.last_tool로 폴백"""
        from seosoyoung.soul.models import ToolResultSSEEvent
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        adapter = SoulEngineAdapter(workspace_dir="/test")

        async def fake_run(prompt, session_id=None, on_progress=None,
                           on_compact=None, on_intervention=None,
                           on_session=None, on_event=None):
            if on_event:
                # 먼저 TOOL_START (tool_name 기록)
                await on_event(EngineEvent(
                    type=EngineEventType.TOOL_START,
                    data={"tool_name": "Glob", "tool_input": {}},
                ))
                # TOOL_RESULT에는 tool_name 없음
                await on_event(EngineEvent(
                    type=EngineEventType.TOOL_RESULT,
                    data={"tool_name": "", "result": "result", "is_error": False},
                ))
            return EngineResult(success=True, output="done")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = fake_run
            events = await collect_events(adapter, "test")

        result_events = [e for e in events if isinstance(e, ToolResultSSEEvent)]
        assert len(result_events) == 1
        # tool_name=""이면 tracker.last_tool="Glob"으로 폴백
        assert result_events[0].tool_name == "Glob"
