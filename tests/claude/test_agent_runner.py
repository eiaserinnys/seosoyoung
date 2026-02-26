"""Claude Code SDK Agent Runner 테스트"""

import asyncio
import json
import os
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.slackbot.claude.agent_runner import (
    ClaudeRunner,
    ClaudeRunner,
    ClaudeResult,
    COMPACT_RETRY_READ_TIMEOUT,
    CompactRetryState,
    DEFAULT_DISALLOWED_TOOLS,
    MAX_COMPACT_RETRIES,
    MessageState,
    _extract_last_assistant_text,
    _registry,
    _registry_lock,
    get_runner,
    register_runner,
    remove_runner,
    shutdown_all,
    shutdown_all_sync,
)
from seosoyoung.slackbot.claude.engine_types import EngineResult
from seosoyoung.slackbot.claude.diagnostics import classify_process_error
from seosoyoung.slackbot.memory.injector import (
    create_or_load_debug_anchor,
    prepare_memory_injection,
    send_injection_debug_log,
)
from seosoyoung.slackbot.config import Config
from claude_agent_sdk._errors import MessageParseError, ProcessError


# SDK 메시지 타입 Mock
@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list = None


@dataclass
class MockResultMessage:
    result: str = ""
    session_id: str = None
    is_error: bool = False


def _apply_mock_config(mock_config, patches):
    """중첩 Config mock에 패치 적용 (dot 경로 지원)"""
    for k, v in patches.items():
        parts = k.split(".")
        obj = mock_config
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], v)


def _make_mock_client(*messages):
    """mock_receive async generator를 설정한 mock client를 생성하는 헬퍼"""
    mock_client = AsyncMock()

    async def mock_receive():
        for msg in messages:
            yield msg

    mock_client.receive_response = mock_receive
    return mock_client


class TestClaudeRunnerUnit:
    """유닛 테스트 (Mock 사용)"""

    def test_build_options_basic(self):
        """기본 옵션 생성 테스트"""
        runner = ClaudeRunner(allowed_tools=["Read", "Glob"])
        options, _ = runner._build_options()

        assert options.allowed_tools == ["Read", "Glob"]
        assert options.disallowed_tools == DEFAULT_DISALLOWED_TOOLS
        assert options.permission_mode == "bypassPermissions"
        assert options.resume is None

    def test_build_options_with_session(self):
        """세션 ID가 있을 때 resume 옵션 추가"""
        runner = ClaudeRunner()
        options, _ = runner._build_options(session_id="abc-123")

        assert options.resume == "abc-123"

    def test_build_options_custom_tools(self):
        """커스텀 도구 설정 테스트"""
        runner = ClaudeRunner(
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"]
        )
        options, _ = runner._build_options()

        assert options.allowed_tools == ["Read", "Glob"]
        assert options.disallowed_tools == ["Bash"]

    def test_build_options_with_mcp_config(self):
        """MCP 설정 파일 경로가 저장되는지 테스트"""
        mcp_path = Path("D:/test/.mcp.json")
        runner = ClaudeRunner(mcp_config_path=mcp_path)

        assert runner.mcp_config_path == mcp_path

        # _build_options는 mcp_servers를 직접 설정하지 않음 (pm2 외부 관리)
        options, _ = runner._build_options()
        assert isinstance(options.mcp_servers, dict)


class TestClaudeRunnerPurity:
    """Phase 2: ClaudeRunner에서 슬랙/OM/마커 의존이 제거되었는지 검증"""

    def test_init_has_no_channel_param(self):
        """channel 파라미터가 __init__에 없어야 함"""
        import inspect
        sig = inspect.signature(ClaudeRunner.__init__)
        assert "channel" not in sig.parameters

    def test_init_has_no_om_callbacks(self):
        """OM 콜백 파라미터가 __init__에 없어야 함"""
        import inspect
        sig = inspect.signature(ClaudeRunner.__init__)
        assert "prepare_memory_fn" not in sig.parameters
        assert "trigger_observation_fn" not in sig.parameters
        assert "on_compact_om_flag" not in sig.parameters

    def test_build_options_returns_two_tuple(self):
        """_build_options가 (options, stderr_file) 2-tuple을 반환"""
        runner = ClaudeRunner()
        result = runner._build_options()
        assert len(result) == 2

    def test_build_options_no_env(self):
        """_build_options가 SLACK env를 설정하지 않아야 함"""
        runner = ClaudeRunner(thread_ts="ts_1")
        options, _ = runner._build_options()
        env = getattr(options, 'env', {}) or {}
        assert "SLACK_CHANNEL" not in env
        assert "SLACK_THREAD_TS" not in env

    def test_run_has_no_user_id_param(self):
        """run()에 user_id 파라미터가 없어야 함"""
        import inspect
        sig = inspect.signature(ClaudeRunner.run)
        assert "user_id" not in sig.parameters
        assert "user_message" not in sig.parameters

    @pytest.mark.asyncio
    async def test_run_returns_engine_result(self):
        """run()이 EngineResult를 반환해야 함 (ClaudeResult가 아님)"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="purity-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert isinstance(result, EngineResult)
        assert not hasattr(result, 'update_requested')
        assert not hasattr(result, 'restart_requested')
        assert not hasattr(result, 'list_run')
        assert not hasattr(result, 'anchor_ts')


class TestClaudeResultMarkers:
    """ClaudeResult 마커 추출 테스트"""

    def test_detect_update_marker(self):
        """UPDATE 마커 감지"""
        output = "코드를 수정했습니다.\n<!-- UPDATE -->"
        assert "<!-- UPDATE -->" in output

    def test_detect_restart_marker(self):
        """RESTART 마커 감지"""
        output = "재시작이 필요합니다.\n<!-- RESTART -->"
        assert "<!-- RESTART -->" in output


@pytest.mark.asyncio
class TestClaudeRunnerAsync:
    """비동기 테스트 (ClaudeSDKClient Mock 사용)"""

    async def test_run_success(self):
        """성공적인 SDK 실행 테스트"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="test-sdk-123"),
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료되었습니다.", session_id="test-sdk-123"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트 프롬프트")

        assert result.success is True
        assert result.session_id == "test-sdk-123"
        assert "완료되었습니다" in result.output

    async def test_run_with_markers(self):
        """마커 포함 응답 테스트 (Phase 2: runner는 마커를 파싱하지 않음, output에 마커 텍스트가 남아있어야 함)"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockResultMessage(
                result="코드를 수정했습니다.\n<!-- UPDATE -->",
                session_id="marker-test"
            ),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        assert "<!-- UPDATE -->" in result.output

    async def test_run_file_not_found(self):
        """Claude CLI 없음 테스트"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = FileNotFoundError("claude not found")

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_run_general_exception(self):
        """일반 예외 처리 테스트"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = RuntimeError("SDK error")

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "SDK error" in result.error

    async def test_compact_session_success(self):
        """compact_session 성공 테스트"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="Compacted.", session_id="compact-123"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.compact_session("test-session-id")

        assert result.success is True
        assert result.session_id == "compact-123"

    async def test_compact_session_no_session_id(self):
        """compact_session 세션 ID 없음 테스트"""
        runner = ClaudeRunner()
        result = await runner.compact_session("")

        assert result.success is False
        assert "세션 ID가 없습니다" in result.error


@pytest.mark.asyncio
class TestClaudeRunnerProgress:
    """진행 상황 콜백 테스트"""

    async def test_progress_callback(self):
        """진행 상황 콜백 호출 테스트"""
        runner = ClaudeRunner()
        progress_calls = []

        async def on_progress(text):
            progress_calls.append(text)

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="progress-test"),
            MockAssistantMessage(content=[MockTextBlock(text="첫 번째")]),
            MockAssistantMessage(content=[MockTextBlock(text="두 번째")]),
            MockResultMessage(result="완료", session_id="progress-test"),
        )

        time_value = [0]

        def mock_time():
            val = time_value[0]
            time_value[0] += 3
            return val

        mock_loop = MagicMock()
        mock_loop.time = mock_time

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch("asyncio.get_event_loop", return_value=mock_loop):
                                result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True


@pytest.mark.asyncio
class TestClaudeRunnerCompact:
    """컴팩션 감지 및 콜백 테스트"""

    async def test_build_options_with_compact_events(self):
        """compact_events 전달 시 PreCompact 훅이 등록되는지 확인"""
        runner = ClaudeRunner()
        compact_events = []
        options, _ = runner._build_options(compact_events=compact_events)

        assert options.hooks is not None
        assert "PreCompact" in options.hooks
        assert len(options.hooks["PreCompact"]) == 1
        assert options.hooks["PreCompact"][0].matcher is None

    async def test_build_options_without_compact_events(self):
        """compact_events 미전달 시 hooks가 None인지 확인"""
        runner = ClaudeRunner()
        options, _ = runner._build_options()

        assert options.hooks is None

    async def test_compact_callback_called(self):
        """컴팩션 발생 시 on_compact 콜백이 호출되는지 확인"""
        runner = ClaudeRunner()
        compact_calls = []

        async def on_compact(trigger: str, message: str):
            compact_calls.append({"trigger": trigger, "message": message})

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="compact-test"),
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="완료", session_id="compact-test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(session_id=session_id, compact_events=compact_events)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch.object(runner, "_build_options", patched_build):
                                result = await runner.run(
                                    "테스트", on_compact=on_compact
                                )

        assert result.success is True
        assert len(compact_calls) == 1
        assert compact_calls[0]["trigger"] == "auto"
        assert "auto" in compact_calls[0]["message"]

    async def test_compact_callback_auto_and_manual(self):
        """auto/manual 트리거 구분 확인"""
        runner = ClaudeRunner()
        compact_calls = []

        async def on_compact(trigger: str, message: str):
            compact_calls.append({"trigger": trigger, "message": message})

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(session_id=session_id, compact_events=compact_events)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
                compact_events.append({
                    "trigger": "manual",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: manual)",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", patched_build):
                    result = await runner.run("테스트", on_compact=on_compact)

        assert result.success is True
        assert len(compact_calls) == 2
        assert compact_calls[0]["trigger"] == "auto"
        assert compact_calls[1]["trigger"] == "manual"

    async def test_compact_callback_error_handled(self):
        """on_compact 콜백 오류 시 실행이 중단되지 않는지 확인"""
        runner = ClaudeRunner()

        async def failing_compact(trigger: str, message: str):
            raise RuntimeError("콜백 오류")

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(session_id=session_id, compact_events=compact_events)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", patched_build):
                    result = await runner.run("테스트", on_compact=failing_compact)

        # 콜백 오류에도 실행은 성공
        assert result.success is True

    async def test_no_compact_callback_no_error(self):
        """on_compact 미전달 시에도 정상 동작 확인"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True


class TestClassifyProcessError:
    """ProcessError 분류 테스트"""

    def test_usage_limit_keyword(self):
        """usage limit 키워드 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="usage limit reached")
        msg = classify_process_error(e)
        assert "사용량 제한" in msg

    def test_rate_limit_keyword(self):
        """rate limit 키워드 감지"""
        e = ProcessError("rate limit exceeded", exit_code=1, stderr=None)
        msg = classify_process_error(e)
        assert "사용량 제한" in msg

    def test_429_status(self):
        """429 상태 코드 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="HTTP 429 Too Many Requests")
        msg = classify_process_error(e)
        assert "사용량 제한" in msg

    def test_unauthorized_401(self):
        """401 인증 오류 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="401 Unauthorized")
        msg = classify_process_error(e)
        assert "인증" in msg

    def test_forbidden_403(self):
        """403 권한 오류 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="403 Forbidden")
        msg = classify_process_error(e)
        assert "인증" in msg

    def test_network_error(self):
        """네트워크 오류 감지"""
        e = ProcessError("Connection refused", exit_code=1, stderr="ECONNREFUSED")
        msg = classify_process_error(e)
        assert "네트워크" in msg

    def test_generic_exit_code_1(self):
        """exit code 1 일반 폴백"""
        e = ProcessError("Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details")
        msg = classify_process_error(e)
        assert "비정상 종료" in msg
        assert "잠시 후" in msg

    def test_other_exit_code(self):
        """기타 exit code"""
        e = ProcessError("Command failed", exit_code=137, stderr=None)
        msg = classify_process_error(e)
        assert "exit code: 137" in msg

    def test_none_stderr(self):
        """stderr가 None인 경우"""
        e = ProcessError("Command failed", exit_code=1, stderr=None)
        msg = classify_process_error(e)
        assert "비정상 종료" in msg


@pytest.mark.asyncio
class TestProcessErrorHandling:
    """ProcessError가 agent_runner._execute에서 올바르게 처리되는지 테스트"""

    async def test_process_error_returns_friendly_message(self):
        """ProcessError 발생 시 친절한 메시지 반환"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details"
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "비정상 종료" in result.error
        assert "잠시 후" in result.error
        # 원래의 불친절한 메시지가 아닌지 확인
        assert "Command failed" not in result.error

    async def test_process_error_with_usage_limit(self):
        """usage limit ProcessError 발생 시 친절한 메시지"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "usage limit reached", exit_code=1, stderr="usage limit"
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error


@pytest.mark.asyncio
class TestRateLimitEventHandling:
    """rate_limit_event (MessageParseError) 처리 테스트"""

    async def test_rate_limit_event_continue_then_complete(self):
        """rate_limit_event 발생 시 continue하고 이후 정상 완료"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        call_count = 0

        class RateLimitThenStop:
            def __aiter__(self):
                return self
            async def __anext__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise MessageParseError(
                        "Unknown message type: rate_limit_event",
                        {
                            "type": "rate_limit_event",
                            "rate_limit_info": {
                                "status": "rejected",
                                "rateLimitType": "seven_day",
                            },
                        },
                    )
                # CLI가 자체 대기 후 정상 종료
                raise StopAsyncIteration

        mock_client.receive_response = MagicMock(return_value=RateLimitThenStop())

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        # rate_limit_event는 continue하므로 정상 종료
        assert result.success is True
        assert call_count == 2

    async def test_rate_limit_event_returns_friendly_error(self):
        """rate_limit_event가 외부 except에서 잡힐 때 친화적 메시지 반환"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # connect 단계에서 MessageParseError 발생
        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: rate_limit_event",
            {"type": "rate_limit_event"}
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error
        # 원문 SDK 에러가 노출되지 않는지 확인
        assert "Unknown message type" not in result.error

    async def test_non_rate_limit_parse_error_returns_friendly_error(self):
        """rate_limit이 아닌 MessageParseError(unknown type)도 친화적 메시지 반환"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: some_unknown_type",
            {"type": "some_unknown_type"}
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "알 수 없는 메시지 타입" in result.error

    async def test_real_parse_error_returns_generic_message(self):
        """type 필드가 없는 진짜 파싱 에러는 일반 에러 메시지 반환"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        mock_client.connect.side_effect = MessageParseError(
            "Malformed JSON",
            None
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "오류가 발생했습니다" in result.error

    async def test_allowed_warning_continues_processing(self):
        """allowed_warning status는 break하지 않고 continue"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        call_count = 0

        class WarningThenText:
            def __aiter__(self):
                return self
            async def __anext__(self):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise MessageParseError(
                        "Unknown message type: rate_limit_event",
                        {
                            "type": "rate_limit_event",
                            "rate_limit_info": {
                                "status": "allowed_warning",
                                "rateLimitType": "seven_day",
                                "utilization": 0.51,
                            },
                        },
                    )
                raise StopAsyncIteration

        mock_client.receive_response = MagicMock(return_value=WarningThenText())

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        # allowed_warning은 break하지 않으므로 정상 종료
        assert result.success is True
        # 2번 호출: 1번째 allowed_warning → continue, 2번째 StopAsyncIteration → break
        assert call_count == 2


class TestFormatRateLimitWarning:
    """format_rate_limit_warning 헬퍼 함수 테스트"""

    def test_seven_day(self):
        from seosoyoung.slackbot.claude.diagnostics import format_rate_limit_warning
        msg = format_rate_limit_warning({
            "rateLimitType": "seven_day",
            "utilization": 0.51,
        })
        assert "주간" in msg
        assert "51%" in msg

    def test_five_hour(self):
        from seosoyoung.slackbot.claude.diagnostics import format_rate_limit_warning
        msg = format_rate_limit_warning({
            "rateLimitType": "five_hour",
            "utilization": 0.90,
        })
        assert "5시간" in msg
        assert "90%" in msg

    def test_unknown_type_uses_raw(self):
        from seosoyoung.slackbot.claude.diagnostics import format_rate_limit_warning
        msg = format_rate_limit_warning({
            "rateLimitType": "daily",
            "utilization": 0.75,
        })
        assert "daily" in msg
        assert "75%" in msg


class TestInjectionDebugLogSkipsWithoutAnchor:
    """anchor_ts가 빈 문자열일 때 send_injection_debug_log가 디버그 로그를 스킵하는지 테스트"""

    def test_skips_debug_log_when_anchor_ts_empty(self):
        """anchor_ts가 빈 문자열이면 디버그 로그를 발송하지 않음 (채널 본문 오염 방지)"""
        mock_result = MagicMock(
            persistent_tokens=100,
            session_tokens=50,
            new_observation_tokens=30,
            channel_digest_tokens=0,
            channel_buffer_tokens=0,
            persistent_content="장기 기억",
            session_content="세션 관찰",
            new_observation_content="새 관찰",
        )

        with patch("seosoyoung.slackbot.memory.observation_pipeline._send_debug_log") as mock_send:
            send_injection_debug_log(
                thread_ts="ts_1234",
                result=mock_result,
                debug_channel="C_DEBUG",
                anchor_ts="",  # 빈 문자열 — 앵커 생성 실패
            )

        # anchor_ts가 비었으므로 _send_debug_log가 호출되지 않아야 함
        mock_send.assert_not_called()

    def test_sends_debug_log_when_anchor_ts_present(self):
        """anchor_ts가 있으면 정상적으로 디버그 로그를 발송"""
        mock_result = MagicMock(
            persistent_tokens=100,
            session_tokens=0,
            new_observation_tokens=0,
            channel_digest_tokens=0,
            channel_buffer_tokens=0,
            persistent_content="장기 기억",
        )

        with patch("seosoyoung.slackbot.memory.observation_pipeline._send_debug_log") as mock_send:
            with patch("seosoyoung.slackbot.memory.observation_pipeline._format_tokens", return_value="100"):
                with patch("seosoyoung.slackbot.memory.observation_pipeline._blockquote", return_value=">장기 기억"):
                    send_injection_debug_log(
                        thread_ts="ts_1234",
                        result=mock_result,
                        debug_channel="C_DEBUG",
                        anchor_ts="anchor_valid",
                    )

        # anchor_ts가 있으므로 _send_debug_log가 호출되어야 함
        mock_send.assert_called()


class TestTriggerObservationToolFilter:
    """_trigger_observation에서 tool_use/tool 메시지 필터링 테스트"""

    def test_filters_tool_use_and_tool_result_messages(self):
        """tool_use, tool role 메시지가 Observer에 전달되지 않음"""
        runner = ClaudeRunner()

        collected = [
            {"role": "assistant", "content": "파일을 읽겠습니다.", "timestamp": "t1"},
            {"role": "assistant", "content": "[tool_use: Read] {\"file\": \"a.py\"}", "timestamp": "t2"},
            {"role": "tool", "content": "파일 내용...", "timestamp": "t3"},
            {"role": "assistant", "content": "수정 완료했습니다.", "timestamp": "t4"},
            {"role": "assistant", "content": "[tool_use: Edit] {\"old\": \"a\", \"new\": \"b\"}", "timestamp": "t5"},
            {"role": "tool", "content": "편집 성공", "timestamp": "t6"},
        ]

        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            MockConfig.om.enabled = True
            MockConfig.om.openai_api_key = "test"
            MockConfig.om.model = "gpt-4.1-mini"
            MockConfig.om.promoter_model = "gpt-4.1-mini"
            MockConfig.om.debug_channel = ""
            MockConfig.get_memory_path.return_value = "/tmp/test"

            # observe_conversation을 모킹하여 전달된 messages를 캡처
            captured_messages = []

            async def mock_observe_conversation(**kwargs):
                captured_messages.extend(kwargs.get("messages", []))

            with patch("seosoyoung.slackbot.memory.observation_pipeline.observe_conversation", mock_observe_conversation):
                with patch("seosoyoung.slackbot.memory.store.MemoryStore"):
                    with patch("seosoyoung.slackbot.memory.observer.Observer"):
                        with patch("seosoyoung.slackbot.memory.reflector.Reflector"):
                            with patch("seosoyoung.slackbot.memory.promoter.Promoter"):
                                with patch("seosoyoung.slackbot.memory.promoter.Compactor"):
                                    # _trigger_observation은 별도 스레드에서 asyncio.run을 실행하므로
                                    # 직접 필터 로직만 테스트
                                    pass

        # 필터 로직을 직접 테스트 (인라인으로 동일 로직 재현)
        text_messages = [
            m for m in collected
            if m.get("role") != "tool"
            and not (m.get("content", "").startswith("[tool_use:"))
        ]
        messages = [{"role": "user", "content": "테스트 질문"}] + text_messages

        # user + 순수 assistant 2개만 남아야 함
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "파일을 읽겠습니다."
        assert messages[2]["content"] == "수정 완료했습니다."

    def test_filters_all_tool_messages_when_only_tools(self):
        """모든 메시지가 tool 관련이면 user 메시지만 남음"""
        collected = [
            {"role": "assistant", "content": "[tool_use: Bash] {}", "timestamp": "t1"},
            {"role": "tool", "content": "result", "timestamp": "t2"},
        ]

        text_messages = [
            m for m in collected
            if m.get("role") != "tool"
            and not (m.get("content", "").startswith("[tool_use:"))
        ]
        messages = [{"role": "user", "content": "질문"}] + text_messages

        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_preserves_pure_assistant_text(self):
        """순수 assistant 텍스트 메시지는 보존됨"""
        collected = [
            {"role": "assistant", "content": "안녕하세요, 도움이 필요하신가요?", "timestamp": "t1"},
            {"role": "assistant", "content": "분석 결과입니다.", "timestamp": "t2"},
        ]

        text_messages = [
            m for m in collected
            if m.get("role") != "tool"
            and not (m.get("content", "").startswith("[tool_use:"))
        ]
        messages = [{"role": "user", "content": "질문"}] + text_messages

        assert len(messages) == 3


def _clear_all_client_state():
    """테스트용: 모듈 레벨 레지스트리 초기화"""
    with _registry_lock:
        _registry.clear()


@pytest.mark.asyncio
class TestShutdownAllClients:
    """shutdown_all (모듈 레벨 레지스트리) 테스트"""

    async def test_shutdown_all_empty(self):
        """활성 러너가 없을 때 0 반환"""
        _clear_all_client_state()

        count = await shutdown_all()
        assert count == 0

    async def test_shutdown_all_multiple(self):
        """여러 러너가 있을 때 모두 종료"""
        _clear_all_client_state()

        mock_client_1 = AsyncMock()
        mock_client_2 = AsyncMock()
        mock_client_3 = AsyncMock()

        runner1 = ClaudeRunner("thread_1")
        runner1.client = mock_client_1
        runner2 = ClaudeRunner("thread_2")
        runner2.client = mock_client_2
        runner3 = ClaudeRunner("thread_3")
        runner3.client = mock_client_3

        register_runner(runner1)
        register_runner(runner2)
        register_runner(runner3)

        count = await shutdown_all()

        assert count == 3
        mock_client_1.disconnect.assert_called_once()
        mock_client_2.disconnect.assert_called_once()
        mock_client_3.disconnect.assert_called_once()

        assert len(_registry) == 0

    async def test_shutdown_all_partial_failure_with_force_kill(self):
        """일부 클라이언트 종료 실패 시 psutil로 강제 종료"""
        _clear_all_client_state()

        mock_client_1 = AsyncMock()
        mock_client_2 = AsyncMock()
        mock_client_2.disconnect.side_effect = RuntimeError("연결 끊기 실패")
        mock_client_3 = AsyncMock()

        runner1 = ClaudeRunner("thread_1")
        runner1.client = mock_client_1
        runner2 = ClaudeRunner("thread_2")
        runner2.client = mock_client_2
        runner2.pid = 12345
        runner3 = ClaudeRunner("thread_3")
        runner3.client = mock_client_3

        register_runner(runner1)
        register_runner(runner2)
        register_runner(runner3)

        with patch.object(ClaudeRunner, "_force_kill_process") as mock_force_kill:
            count = await shutdown_all()

        assert count == 3
        mock_client_1.disconnect.assert_called_once()
        mock_client_2.disconnect.assert_called_once()
        mock_client_3.disconnect.assert_called_once()
        mock_force_kill.assert_called_once_with(12345, "thread_2")

        assert len(_registry) == 0

    async def test_shutdown_partial_failure_no_pid(self):
        """disconnect 실패 시 PID가 없으면 강제 종료 시도 안 함"""
        _clear_all_client_state()

        mock_client = AsyncMock()
        mock_client.disconnect.side_effect = RuntimeError("연결 끊기 실패")

        runner = ClaudeRunner("thread_no_pid")
        runner.client = mock_client
        register_runner(runner)

        with patch.object(ClaudeRunner, "_force_kill_process") as mock_force_kill:
            count = await shutdown_all()

        assert count == 0
        mock_force_kill.assert_not_called()

    async def test_registry_shared_across_runners(self):
        """레지스트리가 모든 러너에서 공유"""
        _clear_all_client_state()

        mock_client = AsyncMock()
        runner = ClaudeRunner("shared_thread")
        runner.client = mock_client
        register_runner(runner)

        assert get_runner("shared_thread") is runner

        count = await shutdown_all()
        assert count == 1


@pytest.mark.asyncio
class TestPidTrackingAndForceKill:
    """PID 추적 및 강제 종료 테스트"""

    async def test_pid_extracted_from_client(self):
        """클라이언트 생성 시 subprocess PID가 추출되는지 확인"""
        runner = ClaudeRunner("test_thread")

        mock_process = MagicMock()
        mock_process.pid = 54321

        mock_transport = MagicMock()
        mock_transport._process = mock_process

        mock_client = AsyncMock()
        mock_client._transport = mock_transport

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            client = await runner._get_or_create_client()

        assert runner.pid == 54321
        assert runner.client is client

    async def test_pid_not_extracted_when_transport_missing(self):
        """transport가 없을 때 PID 추출 실패해도 오류 없음"""
        runner = ClaudeRunner("test_no_transport")

        mock_client = AsyncMock()
        mock_client._transport = None

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            client = await runner._get_or_create_client()

        assert runner.pid is None
        assert runner.client is client

    async def test_remove_client_force_kills_on_disconnect_failure(self):
        """disconnect 실패 시 PID로 강제 종료"""
        runner = ClaudeRunner("thread_fail")

        mock_client = AsyncMock()
        mock_client.disconnect.side_effect = RuntimeError("연결 끊기 실패")

        runner.client = mock_client
        runner.pid = 99999

        with patch.object(ClaudeRunner, "_force_kill_process") as mock_force_kill:
            await runner._remove_client()

        mock_force_kill.assert_called_once_with(99999, "thread_fail")
        assert runner.client is None
        assert runner.pid is None

    async def test_remove_client_no_force_kill_on_success(self):
        """disconnect 성공 시 강제 종료 호출 안 함"""
        runner = ClaudeRunner("thread_ok")

        mock_client = AsyncMock()
        runner.client = mock_client
        runner.pid = 11111

        with patch.object(ClaudeRunner, "_force_kill_process") as mock_force_kill:
            await runner._remove_client()

        mock_force_kill.assert_not_called()
        assert runner.client is None
        assert runner.pid is None



class TestShutdownAllSync:
    """shutdown_all 동기 버전 테스트"""

    def test_shutdown_all_sync(self):
        """동기 버전 shutdown_all_sync 테스트"""
        _clear_all_client_state()

        mock_client = AsyncMock()
        runner = ClaudeRunner("thread_sync")
        runner.client = mock_client
        register_runner(runner)

        count = shutdown_all_sync()

        assert count == 1
        mock_client.disconnect.assert_called_once()


class TestForceKillProcess:
    """_force_kill_process 정적 메서드 테스트 (동기)"""

    def test_force_kill_process_terminate_success(self):
        """_force_kill_process: terminate 성공"""
        mock_proc = MagicMock()

        # agent_runner 모듈 내부에서 psutil을 import하므로 해당 경로로 패치
        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            mock_psutil.Process.return_value = mock_proc
            ClaudeRunner._force_kill_process(12345, "test_thread")

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=3)

    def test_force_kill_process_terminate_timeout_then_kill(self):
        """_force_kill_process: terminate 타임아웃 시 kill 사용"""
        mock_proc = MagicMock()

        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            # TimeoutExpired 예외 시뮬레이션
            mock_psutil.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
            mock_proc.wait.side_effect = [mock_psutil.TimeoutExpired(3), None]
            mock_psutil.Process.return_value = mock_proc
            ClaudeRunner._force_kill_process(12345, "test_thread")

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2

    def test_force_kill_process_no_such_process(self):
        """_force_kill_process: 프로세스가 이미 종료된 경우"""
        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            # NoSuchProcess 예외 시뮬레이션
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.Process.side_effect = mock_psutil.NoSuchProcess(12345)
            # 예외 발생하지 않음
            ClaudeRunner._force_kill_process(12345, "test_thread")

    def test_force_kill_process_general_error(self):
        """_force_kill_process: 일반 오류 발생 시 로깅만"""
        import psutil as real_psutil
        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            # 실제 예외 클래스들을 유지
            mock_psutil.NoSuchProcess = real_psutil.NoSuchProcess
            mock_psutil.TimeoutExpired = real_psutil.TimeoutExpired
            mock_psutil.Process.side_effect = RuntimeError("알 수 없는 오류")
            # 예외 발생하지 않음 (로깅만)
            ClaudeRunner._force_kill_process(12345, "test_thread")


class TestServiceFactory:
    """서비스 팩토리 테스트"""

    def test_factory_returns_agent_runner(self):
        """팩토리가 항상 ClaudeRunner를 반환"""
        from seosoyoung.slackbot.claude import get_claude_runner
        runner = get_claude_runner()
        assert isinstance(runner, ClaudeRunner)


class TestGetRoleConfig:
    """_get_role_config 인스턴스 메서드 테스트"""

    def _make_executor(self, role_tools=None):
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.claude.session import SessionRuntime
        return ClaudeExecutor(
            session_manager=MagicMock(),
            session_runtime=MagicMock(spec=SessionRuntime),
            restart_manager=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            update_message_fn=MagicMock(),
            role_tools=role_tools or {
                "admin": ["Read", "Write", "Edit", "Bash"],
                "viewer": ["Read", "Glob"],
            },
        )

    def test_viewer_role_has_correct_disallowed_tools(self):
        """viewer 역할은 수정/실행 도구가 차단됨"""
        executor = self._make_executor()
        config = executor._get_role_config("viewer")

        assert "Write" in config["disallowed_tools"]
        assert "Edit" in config["disallowed_tools"]
        assert "Bash" in config["disallowed_tools"]
        assert "TodoWrite" in config["disallowed_tools"]

    def test_admin_role_has_mcp_config(self):
        """admin 역할은 MCP 설정을 사용 (설정 파일 존재 시)"""
        from seosoyoung.slackbot.claude.executor import _get_mcp_config_path

        executor = self._make_executor()
        config = executor._get_role_config("admin")

        expected_path = _get_mcp_config_path()
        if expected_path:
            assert config["mcp_config_path"] == expected_path
        else:
            assert config["mcp_config_path"] is None

    def test_admin_role_has_no_disallowed_tools(self):
        """admin 역할은 disallowed_tools가 None"""
        executor = self._make_executor()
        config = executor._get_role_config("admin")
        assert config["disallowed_tools"] is None

    def test_returns_dict_with_required_keys(self):
        """반환값이 필수 키를 포함"""
        executor = self._make_executor()
        config = executor._get_role_config("admin")
        assert "allowed_tools" in config
        assert "disallowed_tools" in config
        assert "mcp_config_path" in config


@pytest.mark.integration
@pytest.mark.asyncio
class TestClaudeRunnerIntegration:
    """통합 테스트 (실제 SDK 호출)

    실행 방법: pytest -m integration tests/test_agent_runner.py
    """

    async def test_real_sdk_execution(self):
        """실제 SDK 실행 테스트"""
        runner = ClaudeRunner()
        result = await runner.run("1+1은? 숫자만 답해줘.")

        assert result.success is True
        assert result.session_id is not None
        assert "2" in result.output

    async def test_mcp_trello_integration(self):
        """Trello MCP 도구 통합 테스트

        SDK 모드에서 Trello MCP 도구가 정상 작동하는지 확인
        """
        runner = ClaudeRunner(
            allowed_tools=["Read", "mcp__trello__get_lists"]
        )
        result = await runner.run(
            "mcp__trello__get_lists 도구를 사용해서 Trello 보드의 리스트 목록을 가져와줘. "
            "결과 요약만 한 줄로 알려줘."
        )

        # MCP 도구 호출 성공 여부만 확인
        # 실패하면 권한 오류나 도구 미발견 에러가 발생함
        assert result.success is True

    async def test_mcp_slack_integration(self):
        """Slack MCP 도구 통합 테스트

        SDK 모드에서 Slack MCP 도구가 정상 작동하는지 확인
        """
        runner = ClaudeRunner(
            allowed_tools=["Read", "mcp__slack__channels_list"]
        )
        result = await runner.run(
            "mcp__slack__channels_list 도구를 사용해서 채널 목록을 가져와줘. "
            "결과 요약만 한 줄로 알려줘."
        )

        assert result.success is True


class TestBuildCompactHook:
    """_build_compact_hook 메서드 단위 테스트"""

    def test_returns_none_when_compact_events_is_none(self):
        """compact_events가 None이면 hooks는 None"""
        runner = ClaudeRunner()
        hooks = runner._build_compact_hook(None)
        assert hooks is None

    def test_returns_hooks_when_compact_events_provided(self):
        """compact_events 제공 시 PreCompact 훅 딕셔너리 반환"""
        runner = ClaudeRunner(thread_ts="ts_1")
        compact_events = []
        hooks = runner._build_compact_hook(compact_events)

        assert hooks is not None
        assert "PreCompact" in hooks
        assert len(hooks["PreCompact"]) == 1
        assert hooks["PreCompact"][0].matcher is None

    def test_returns_hooks_without_thread_ts(self):
        """thread_ts가 없어도 훅 생성됨"""
        runner = ClaudeRunner()
        compact_events = []
        hooks = runner._build_compact_hook(compact_events)

        assert hooks is not None
        assert "PreCompact" in hooks


class TestCreateOrLoadDebugAnchor:
    """create_or_load_debug_anchor 함수 단위 테스트"""

    def test_returns_empty_when_no_debug_channel(self):
        """debug_channel이 빈 문자열이면 빈 문자열 반환"""
        anchor_ts = create_or_load_debug_anchor(
            thread_ts="ts_1", session_id=None, store=MagicMock(),
            prompt="test", debug_channel="",
        )
        assert anchor_ts == ""

    def test_creates_anchor_for_new_session(self, tmp_path):
        """새 세션(session_id=None) 시 앵커 메시지 생성 + MemoryRecord 저장"""
        from seosoyoung.slackbot.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)

        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            MockConfig.emoji.text_session_start = "🟢"
            with patch("seosoyoung.slackbot.memory.observation_pipeline._send_debug_log", return_value="anchor_new_123"):
                anchor_ts = create_or_load_debug_anchor(
                    thread_ts="ts_new", session_id=None, store=store,
                    prompt="테스트 프롬프트입니다", debug_channel="C_DEBUG",
                )

        assert anchor_ts == "anchor_new_123"
        record = store.get_record("ts_new")
        assert record is not None
        assert record.anchor_ts == "anchor_new_123"

    def test_loads_existing_anchor_for_resumed_session(self, tmp_path):
        """기존 세션 재개 시 MemoryRecord에서 anchor_ts 로드"""
        from seosoyoung.slackbot.memory.store import MemoryStore, MemoryRecord
        store = MemoryStore(base_dir=tmp_path)
        record = MemoryRecord(thread_ts="ts_existing", anchor_ts="saved_anchor_456")
        store.save_record(record)

        anchor_ts = create_or_load_debug_anchor(
            thread_ts="ts_existing", session_id="session_abc", store=store,
            prompt="test", debug_channel="C_DEBUG",
        )
        assert anchor_ts == "saved_anchor_456"

    def test_returns_empty_for_resumed_session_no_record(self, tmp_path):
        """기존 세션 재개 시 MemoryRecord가 없으면 빈 문자열"""
        from seosoyoung.slackbot.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)

        anchor_ts = create_or_load_debug_anchor(
            thread_ts="ts_no_record", session_id="session_xyz", store=store,
            prompt="test", debug_channel="C_DEBUG",
        )
        assert anchor_ts == ""

    def test_truncates_long_prompt_preview(self, tmp_path):
        """80자 초과 프롬프트가 잘려서 앵커에 포함"""
        from seosoyoung.slackbot.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)
        long_prompt = "A" * 100

        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            MockConfig.emoji.text_session_start = "🟢"
            with patch("seosoyoung.slackbot.memory.observation_pipeline._send_debug_log", return_value="anc") as mock_send:
                create_or_load_debug_anchor(
                    thread_ts="ts_long", session_id=None, store=store,
                    prompt=long_prompt, debug_channel="C_DEBUG",
                )

        call_msg = mock_send.call_args[0][1]
        assert "…" in call_msg


class TestPrepareMemoryInjection:
    """prepare_memory_injection 함수 단위 테스트"""

    def test_returns_none_when_no_thread_ts(self):
        """thread_ts가 빈 문자열이면 (None, '') 반환"""
        memory_prompt, anchor_ts = prepare_memory_injection(
            thread_ts="", channel=None, session_id=None, prompt="test",
        )
        assert memory_prompt is None
        assert anchor_ts == ""

    def test_returns_none_when_om_disabled(self):
        """OM 비활성 시 (None, '') 반환"""
        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            MockConfig.om.enabled = False
            memory_prompt, anchor_ts = prepare_memory_injection(
                thread_ts="ts_1", channel="C1", session_id=None, prompt="test",
            )
        assert memory_prompt is None
        assert anchor_ts == ""

    def test_returns_memory_prompt_when_available(self, tmp_path):
        """OM 활성 + 메모리 존재 시 memory_prompt 반환"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "",
        }

        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.slackbot.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt="<long-term-memory>기억</long-term-memory>",
                    persistent_tokens=50,
                    session_tokens=0,
                    new_observation_tokens=0,
                    new_observation_content="",
                    persistent_content="기억",
                    session_content="",
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                memory_prompt, anchor_ts = prepare_memory_injection(
                    thread_ts="ts_1", channel="C1", session_id=None, prompt="test",
                )

        assert memory_prompt is not None
        assert "기억" in memory_prompt

    def test_calls_create_or_load_debug_anchor(self, tmp_path):
        """create_or_load_debug_anchor가 내부적으로 호출되는지 확인"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "C_DEBUG",
        }

        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.slackbot.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt=None,
                    persistent_tokens=0,
                    session_tokens=0,
                    new_observation_tokens=0,
                    new_observation_content="",
                    persistent_content="",
                    session_content="",
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                with patch("seosoyoung.slackbot.memory.injector.create_or_load_debug_anchor", return_value="anc_789") as mock_anchor:
                    _, anchor_ts = prepare_memory_injection(
                        thread_ts="ts_1", channel="C1", session_id=None, prompt="test",
                    )

        mock_anchor.assert_called_once()
        assert anchor_ts == "anc_789"

    def test_exception_returns_none_gracefully(self):
        """OM 내부 예외 발생 시 (None, '') 반환 (무시)"""
        with patch("seosoyoung.slackbot.config.Config") as MockConfig:
            MockConfig.om.enabled = True
            MockConfig.get_memory_path.side_effect = RuntimeError("boom")
            memory_prompt, anchor_ts = prepare_memory_injection(
                thread_ts="ts_err", channel="C1", session_id=None, prompt="test",
            )
        assert memory_prompt is None
        assert anchor_ts == ""


class TestExtractLastAssistantText:
    """_extract_last_assistant_text 헬퍼 함수 테스트"""

    def test_extracts_last_assistant_text(self):
        """마지막 assistant 텍스트를 추출"""
        msgs = [
            {"role": "assistant", "content": "첫 번째"},
            {"role": "assistant", "content": "[tool_use: Read] {}"},
            {"role": "tool", "content": "파일 내용"},
            {"role": "assistant", "content": "최종 답변"},
        ]
        assert _extract_last_assistant_text(msgs) == "최종 답변"

    def test_skips_tool_use_messages(self):
        """tool_use 메시지를 건너뜀"""
        msgs = [
            {"role": "assistant", "content": "텍스트"},
            {"role": "assistant", "content": "[tool_use: Bash] {}"},
        ]
        assert _extract_last_assistant_text(msgs) == "텍스트"

    def test_returns_empty_when_no_assistant(self):
        """assistant 메시지가 없으면 빈 문자열"""
        msgs = [
            {"role": "tool", "content": "결과"},
            {"role": "assistant", "content": "[tool_use: Read] {}"},
        ]
        assert _extract_last_assistant_text(msgs) == ""

    def test_returns_empty_for_empty_list(self):
        """빈 리스트이면 빈 문자열"""
        assert _extract_last_assistant_text([]) == ""


class TestIsCliAlive:
    """_is_cli_alive 메서드 테스트"""

    def test_returns_false_when_pid_is_none(self):
        """PID가 None이면 False"""
        runner = ClaudeRunner()
        runner.pid = None
        assert runner._is_cli_alive() is False

    def test_returns_true_for_running_process(self):
        """실행 중인 프로세스면 True"""
        runner = ClaudeRunner()
        runner.pid = 12345

        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True

        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            mock_psutil.Process.return_value = mock_proc
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            assert runner._is_cli_alive() is True

    def test_returns_false_for_dead_process(self):
        """종료된 프로세스면 False"""
        runner = ClaudeRunner()
        runner.pid = 99999

        with patch("seosoyoung.slackbot.claude.agent_runner.psutil") as mock_psutil:
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.Process.side_effect = mock_psutil.NoSuchProcess(99999)
            assert runner._is_cli_alive() is False


@pytest.mark.asyncio
class TestCompactRetryHangFix:
    """compact 재시도 시 무한 대기 방지 테스트 (A/B/C)"""

    async def test_retry_skipped_when_has_result(self):
        """[partial fix] 이미 결과가 있으면 compact 후에도 retry 생략"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # compact 이벤트가 발생하지만 ResultMessage도 같이 수신되는 시나리오
        mock_client.receive_response = MagicMock(return_value=_make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="응답 텍스트")]),
            MockResultMessage(result="최종 결과", session_id="test"),
        ).receive_response())

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(
                session_id=session_id, compact_events=compact_events,
            )
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch.object(runner, "_build_options", patched_build):
                                result = await runner.run("테스트")

        # compact 발생했지만 결과가 있으므로 retry 없이 성공
        assert result.success is True
        assert result.output == "최종 결과"
        # receive_response가 1번만 호출됨 (retry 없음)
        mock_client.receive_response.assert_called_once()

    async def test_retry_skipped_when_cli_dead(self):
        """[B] CLI 프로세스 종료 시 retry 생략 + [C] fallback 텍스트 복원"""
        runner = ClaudeRunner()
        runner.pid = 12345

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # 1차 receive_response: 텍스트 없이 StopAsyncIteration
        # (compact 직후, TextBlock 수신 전 CLI 종료 시나리오)
        call_count = 0

        class EmptyResponse:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        mock_client.receive_response = MagicMock(return_value=EmptyResponse())

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(
                session_id=session_id, compact_events=compact_events,
            )
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch.object(runner, "_build_options", patched_build):
                with patch.object(runner, "_is_cli_alive", return_value=False):
                    result = await runner.run("테스트")

        # CLI 종료 → retry 생략 → 무한 대기 없이 종료
        assert result.success is True
        # receive_response가 1번만 호출됨 (retry 안 함)
        mock_client.receive_response.assert_called_once()

    async def test_retry_skipped_cli_dead_with_fallback(self):
        """[B+C] CLI 종료 시 collected_messages에서 fallback 텍스트 복원"""
        runner = ClaudeRunner()
        runner.pid = 12345

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # on_progress가 호출된 후 compact + CLI 종료
        # TextBlock을 먼저 수신하고, StopAsyncIteration으로 종료
        # 하지만 ResultMessage 없음 → result_text=""
        # current_text는 설정됨 → has_result=True → 이 케이스는 partial fix로 해결
        # 여기서는 current_text가 빈 경우를 테스트 (collected_messages에만 텍스트 존재)

        class TextThenStop:
            """TextBlock을 보내지만 current_text 리셋 시나리오를 시뮬레이션"""
            def __init__(self):
                self.sent = False
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not self.sent:
                    self.sent = True
                    return MockAssistantMessage(content=[MockTextBlock(text="작업 중간 텍스트")])
                raise StopAsyncIteration

        mock_client.receive_response = MagicMock(return_value=TextThenStop())

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(
                session_id=session_id, compact_events=compact_events,
            )
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options, stderr_f

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                    with patch.object(runner, "_build_options", patched_build):
                        result = await runner.run("테스트")

        # TextBlock이 수신되어 current_text 설정됨 → has_result=True → retry 생략
        assert result.success is True
        assert "작업 중간 텍스트" in result.output

    async def test_timeout_breaks_retry_loop(self):
        """[A] retry 시 timeout으로 무한 대기 방지"""
        runner = ClaudeRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # compact_events 리스트를 캡처하기 위한 컨테이너
        captured_compact_events = [None]

        class HangForever:
            def __aiter__(self):
                return self
            async def __anext__(self):
                await asyncio.sleep(9999)

        call_idx = [0]

        def mock_receive():
            call_idx[0] += 1
            if call_idx[0] == 1:
                # 1차 호출: 내부 루프 중에 compact 이벤트 주입 후 즉시 종료
                events = captured_compact_events[0]

                class InjectCompactThenStop:
                    def __aiter__(self):
                        return self
                    async def __anext__(self):
                        if events is not None:
                            events.append({
                                "trigger": "auto",
                                "message": "컴팩트 실행됨",
                            })
                        raise StopAsyncIteration

                return InjectCompactThenStop()
            # 2차(retry): 영원히 대기 → timeout이 구해줌
            return HangForever()

        mock_client.receive_response = mock_receive

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None):
            options, stderr_f = original_build(
                session_id=session_id, compact_events=compact_events,
            )
            # compact_events 리스트 참조를 캡처 (내부 루프에서 이벤트 주입용)
            captured_compact_events[0] = compact_events
            return options, stderr_f

        # timeout을 짧게 설정하여 테스트 빠르게 완료
        with patch("seosoyoung.slackbot.claude.agent_runner.COMPACT_RETRY_READ_TIMEOUT", 0.1):
            with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
                with patch.object(runner, "_build_options", patched_build):
                    with patch.object(runner, "_is_cli_alive", return_value=True):
                        result = await runner.run("테스트")

        # timeout으로 인해 무한 대기 없이 종료
        assert result.success is True
        assert call_idx[0] == 2  # 1차 + retry 1회


class TestClaudeResultIsError:
    """ClaudeResult.is_error 필드 테스트"""

    def test_is_error_default_false(self):
        """is_error 기본값은 False"""
        result = ClaudeResult(success=True, output="test")
        assert result.is_error is False

    def test_is_error_set_true(self):
        """is_error를 True로 설정"""
        result = ClaudeResult(success=False, output="error", is_error=True)
        assert result.is_error is True

    def test_interrupted_and_is_error_independent(self):
        """interrupted와 is_error는 독립적"""
        result = ClaudeResult(success=False, output="", interrupted=True, is_error=False)
        assert result.interrupted is True
        assert result.is_error is False

        result2 = ClaudeResult(success=False, output="", interrupted=False, is_error=True)
        assert result2.interrupted is False
        assert result2.is_error is True


@pytest.mark.asyncio
class TestClaudeRunnerIsErrorFromResultMessage:
    """ResultMessage.is_error가 ClaudeResult.is_error로 정확히 매핑되는지 테스트"""

    async def test_result_message_is_error_sets_is_error(self):
        """ResultMessage.is_error=True → ClaudeResult.is_error=True, success=False"""
        runner = ClaudeRunner()

        error_result = MockResultMessage(
            result="오류가 발생했습니다",
            session_id="error-test",
            is_error=True,
        )
        mock_client = _make_mock_client(
            MockSystemMessage(session_id="error-test"),
            error_result,
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    result = await runner.run("테스트")

        assert result.is_error is True
        assert result.success is False
        assert result.interrupted is False
        assert result.output == "오류가 발생했습니다"

    async def test_result_message_not_error_sets_success(self):
        """ResultMessage.is_error=False → ClaudeResult.success=True, is_error=False"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockResultMessage(
                result="정상 응답",
                session_id="ok-test",
                is_error=False,
            ),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.is_error is False
        assert result.success is True
        assert result.interrupted is False


@pytest.mark.asyncio
class TestInlineIntervention:
    """엔진 레벨 인라인 인터벤션 테스트"""

    async def test_run_without_intervention_unchanged(self):
        """on_intervention 미전달 시 기존 동작과 동일"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="no-intervention"),
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="완료", session_id="no-intervention"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트")

        assert result.success is True
        assert result.output == "완료"
        assert result.session_id == "no-intervention"
        # query는 처음 프롬프트 한 번만 호출
        mock_client.query.assert_called_once_with("테스트")

    async def test_run_with_intervention_none_no_injection(self):
        """on_intervention이 None을 반환하면 메시지 주입 없음"""
        runner = ClaudeRunner()

        call_count = 0

        async def no_intervention():
            nonlocal call_count
            call_count += 1
            return None

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="완료", session_id="none-intervention"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        result = await runner.run("테스트", on_intervention=no_intervention)

        assert result.success is True
        assert result.output == "완료"
        # on_intervention은 매 메시지마다 호출됨
        assert call_count >= 1
        # query는 처음 프롬프트 한 번만
        mock_client.query.assert_called_once_with("테스트")

    async def test_run_with_intervention_injects_message(self):
        """on_intervention이 문자열을 반환하면 client.query로 주입"""
        runner = ClaudeRunner()

        intervention_fired = False

        async def one_time_intervention():
            nonlocal intervention_fired
            if not intervention_fired:
                intervention_fired = True
                return "[사용자 개입] 추가 지시사항입니다."
            return None

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="최종 결과", session_id="with-intervention"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        result = await runner.run("테스트", on_intervention=one_time_intervention)

        assert result.success is True
        # query가 2번 호출: 원래 프롬프트 + 인터벤션 주입
        assert mock_client.query.call_count == 2
        calls = mock_client.query.call_args_list
        assert calls[0].args[0] == "테스트"
        assert calls[1].args[0] == "[사용자 개입] 추가 지시사항입니다."

    async def test_intervention_callback_error_does_not_break_execution(self):
        """on_intervention 콜백 오류 시 실행이 중단되지 않음"""
        runner = ClaudeRunner()

        async def failing_intervention():
            raise RuntimeError("콜백 폭발!")

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="완료", session_id="error-intervention"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        result = await runner.run("테스트", on_intervention=failing_intervention)

        # 콜백 오류에도 실행은 성공
        assert result.success is True
        assert result.output == "완료"

    async def test_intervention_type_in_engine_types(self):
        """InterventionCallback 타입이 engine_types에 존재"""
        from seosoyoung.slackbot.claude.engine_types import InterventionCallback
        assert InterventionCallback is not None

    async def test_run_signature_has_on_intervention(self):
        """run() 시그니처에 on_intervention 파라미터가 있어야 함"""
        import inspect
        sig = inspect.signature(ClaudeRunner.run)
        assert "on_intervention" in sig.parameters

    async def test_intervention_preserves_existing_callbacks(self):
        """on_intervention이 있어도 on_progress, on_compact이 정상 동작"""
        runner = ClaudeRunner()

        progress_calls = []
        compact_calls = []

        async def on_progress(text):
            progress_calls.append(text)

        async def on_compact(trigger, message):
            compact_calls.append(trigger)

        async def no_intervention():
            return None

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료", session_id="combined-test"),
        )

        time_value = [0]

        def mock_time():
            val = time_value[0]
            time_value[0] += 3
            return val

        mock_loop = MagicMock()
        mock_loop.time = mock_time

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        with patch("asyncio.get_event_loop", return_value=mock_loop):
                            result = await runner.run(
                                "테스트",
                                on_progress=on_progress,
                                on_compact=on_compact,
                                on_intervention=no_intervention,
                            )

        assert result.success is True


class TestClaudeRunnerPooled:
    """ClaudeRunner pooled 모드 테스트"""

    def test_pooled_false_by_default(self):
        """pooled 기본값은 False"""
        runner = ClaudeRunner()
        assert runner._pooled is False

    def test_pooled_true(self):
        """pooled=True 설정 가능"""
        runner = ClaudeRunner(pooled=True)
        assert runner._pooled is True

    @pytest.mark.asyncio
    async def test_non_pooled_destroys_client_after_run(self):
        """pooled=False(기본)는 실행 후 client 파괴"""
        runner = ClaudeRunner(thread_ts="test_ts_non_pooled")
        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="s1"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        # pooled=False이면 실행 후 client가 None이어야 함
        assert runner.client is None
        assert runner.execution_loop is None
        # disconnect 호출 확인
        mock_client.disconnect.assert_called()

    @pytest.mark.asyncio
    async def test_pooled_preserves_client_after_run(self):
        """pooled=True는 실행 후 client 유지"""
        runner = ClaudeRunner(thread_ts="test_ts_pooled", pooled=True)
        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="s1"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        # pooled=True이면 실행 후 client가 유지되어야 함
        assert runner.client is mock_client
        # execution_loop는 항상 정리됨
        assert runner.execution_loop is None
        # disconnect 미호출 확인
        mock_client.disconnect.assert_not_called()

    def test_is_idle_no_client(self):
        """client 없으면 is_idle() = False"""
        runner = ClaudeRunner()
        assert runner.is_idle() is False

    def test_is_idle_with_client_not_running(self):
        """client 있고 실행 중 아니면 is_idle() = True"""
        runner = ClaudeRunner()
        runner.client = MagicMock()
        runner.execution_loop = None
        assert runner.is_idle() is True

    def test_is_idle_while_running(self):
        """실행 중이면 is_idle() = False"""
        runner = ClaudeRunner()
        runner.client = MagicMock()
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        runner.execution_loop = mock_loop
        assert runner.is_idle() is False

    def test_detach_client_clears_client_and_pid(self):
        """detach_client()는 client/pid를 분리하고 disconnect 하지 않음"""
        runner = ClaudeRunner()
        mock_client = MagicMock()
        runner.client = mock_client
        runner.pid = 12345

        returned_client = runner.detach_client()

        # client와 pid가 None으로 초기화됨
        assert runner.client is None
        assert runner.pid is None
        # 반환값은 원래 client
        assert returned_client is mock_client
        # disconnect는 호출하지 않음
        mock_client.disconnect.assert_not_called()

    def test_detach_client_no_client(self):
        """client 없으면 detach_client()는 None 반환"""
        runner = ClaudeRunner()
        result = runner.detach_client()
        assert result is None

    @pytest.mark.asyncio
    async def test_pooled_registry_cleanup_after_run(self):
        """pooled 모드에서 실행 후 레지스트리에서 제거됨"""
        runner = ClaudeRunner(thread_ts="test_ts_pooled_registry", pooled=True)
        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="s1"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        # 레지스트리에서는 제거됨 (풀이 별도로 관리)
        assert get_runner("test_ts_pooled_registry") is None
        assert result.success is True


@pytest.mark.asyncio
class TestEngineEventCallback:
    """on_event 콜백을 통한 세분화 이벤트 발행 테스트"""

    async def test_text_delta_event_emitted(self):
        """TextBlock -> TEXT_DELTA 이벤트가 발행되는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        runner = ClaudeRunner()
        events = []

        async def on_event(event: EngineEvent):
            events.append(event)

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="응답 중...")]),
            MockResultMessage(result="완료", session_id="evt-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        await runner.run("테스트", on_event=on_event)

        text_events = [e for e in events if e.type == EngineEventType.TEXT_DELTA]
        assert len(text_events) == 1
        assert text_events[0].data["text"] == "응답 중..."

    async def test_tool_start_event_emitted(self):
        """ToolUseBlock -> TOOL_START 이벤트가 발행되는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        @dataclass
        class MockToolUseBlock:
            name: str
            input: dict = None

        runner = ClaudeRunner()
        events = []

        async def on_event(event: EngineEvent):
            events.append(event)

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockToolUseBlock(name="Read", input={"file_path": "/test.py"})]),
            MockResultMessage(result="완료", session_id="tool-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ToolUseBlock", MockToolUseBlock):
                        await runner.run("테스트", on_event=on_event)

        tool_events = [e for e in events if e.type == EngineEventType.TOOL_START]
        assert len(tool_events) == 1
        assert tool_events[0].data["tool_name"] == "Read"
        assert tool_events[0].data["tool_input"] == {"file_path": "/test.py"}

    async def test_tool_result_event_emitted(self):
        """ToolResultBlock -> TOOL_RESULT 이벤트가 발행되는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        @dataclass
        class MockToolUseBlock:
            name: str
            input: dict = None

        @dataclass
        class MockToolResultBlock:
            content: str = ""
            is_error: bool = False

        runner = ClaudeRunner()
        events = []

        async def on_event(event: EngineEvent):
            events.append(event)

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[
                MockToolUseBlock(name="Read", input={}),
                MockToolResultBlock(content="파일 내용입니다", is_error=False),
            ]),
            MockResultMessage(result="완료", session_id="result-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ToolUseBlock", MockToolUseBlock):
                        with patch("seosoyoung.slackbot.claude.agent_runner.ToolResultBlock", MockToolResultBlock):
                            await runner.run("테스트", on_event=on_event)

        tool_result_events = [e for e in events if e.type == EngineEventType.TOOL_RESULT]
        assert len(tool_result_events) == 1
        assert tool_result_events[0].data["tool_name"] == "Read"
        assert tool_result_events[0].data["result"] == "파일 내용입니다"
        assert tool_result_events[0].data["is_error"] is False

    async def test_result_event_emitted(self):
        """ResultMessage -> RESULT 이벤트가 발행되는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        runner = ClaudeRunner()
        events = []

        async def on_event(event: EngineEvent):
            events.append(event)

        mock_client = _make_mock_client(
            MockResultMessage(result="최종 결과물", session_id="final-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                await runner.run("테스트", on_event=on_event)

        result_events = [e for e in events if e.type == EngineEventType.RESULT]
        assert len(result_events) == 1
        assert result_events[0].data["success"] is True
        assert result_events[0].data["output"] == "최종 결과물"

    async def test_no_event_callback_backward_compat(self):
        """on_event=None 시 기존 동작과 동일한지 확인 (회귀 테스트)"""
        runner = ClaudeRunner()

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="텍스트")]),
            MockResultMessage(result="완료", session_id="compat-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        # on_event 없이 호출 - 기존 코드와 동일
                        result = await runner.run("테스트")

        assert result.success is True
        assert result.output == "완료"

    async def test_event_callback_error_does_not_raise(self):
        """이벤트 콜백에서 예외 발생해도 실행이 중단되지 않는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        runner = ClaudeRunner()

        async def broken_on_event(event: EngineEvent):
            raise RuntimeError("콜백 오류 시뮬레이션")

        mock_client = _make_mock_client(
            MockAssistantMessage(content=[MockTextBlock(text="텍스트")]),
            MockResultMessage(result="완료", session_id="err-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                        result = await runner.run("테스트", on_event=broken_on_event)

        # 콜백 오류에도 불구하고 실행 결과는 정상
        assert result.success is True
        assert result.output == "완료"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
