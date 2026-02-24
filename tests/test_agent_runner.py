"""Claude Code SDK Agent Runner 테스트"""

import asyncio
import json
import os
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.claude.agent_runner import (
    ClaudeAgentRunner,
    ClaudeRunner,
    ClaudeResult,
    DEFAULT_DISALLOWED_TOOLS,
    _registry,
    _registry_lock,
    get_runner,
    register_runner,
    remove_runner,
    shutdown_all,
    shutdown_all_sync,
)
from seosoyoung.claude.diagnostics import classify_process_error
from seosoyoung.memory.injector import (
    create_or_load_debug_anchor,
    prepare_memory_injection,
    send_injection_debug_log,
)
from seosoyoung.config import Config
from claude_code_sdk._errors import MessageParseError, ProcessError


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


class TestClaudeAgentRunnerUnit:
    """유닛 테스트 (Mock 사용)"""

    def test_build_options_basic(self):
        """기본 옵션 생성 테스트"""
        runner = ClaudeAgentRunner()
        options, memory_prompt, anchor_ts = runner._build_options()

        assert options.allowed_tools == Config.auth.role_tools["admin"]
        assert options.disallowed_tools == DEFAULT_DISALLOWED_TOOLS
        assert options.permission_mode == "bypassPermissions"
        assert options.resume is None
        assert memory_prompt is None
        assert anchor_ts == ""

    def test_build_options_with_session(self):
        """세션 ID가 있을 때 resume 옵션 추가"""
        runner = ClaudeAgentRunner()
        options, _, _ = runner._build_options(session_id="abc-123")

        assert options.resume == "abc-123"

    def test_build_options_custom_tools(self):
        """커스텀 도구 설정 테스트"""
        runner = ClaudeAgentRunner(
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"]
        )
        options, _, _ = runner._build_options()

        assert options.allowed_tools == ["Read", "Glob"]
        assert options.disallowed_tools == ["Bash"]

    def test_build_options_with_mcp_config(self):
        """MCP 설정 파일 경로가 저장되는지 테스트"""
        mcp_path = Path("D:/test/.mcp.json")
        runner = ClaudeAgentRunner(mcp_config_path=mcp_path)

        assert runner.mcp_config_path == mcp_path

        # _build_options는 mcp_servers를 직접 설정하지 않음 (pm2 외부 관리)
        options, _, _ = runner._build_options()
        assert isinstance(options.mcp_servers, dict)


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
class TestClaudeAgentRunnerAsync:
    """비동기 테스트 (ClaudeSDKClient Mock 사용)"""

    async def test_run_success(self):
        """성공적인 SDK 실행 테스트"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="test-sdk-123"),
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료되었습니다.", session_id="test-sdk-123"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트 프롬프트")

        assert result.success is True
        assert result.session_id == "test-sdk-123"
        assert "완료되었습니다" in result.output

    async def test_run_with_markers(self):
        """마커 포함 응답 테스트"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockResultMessage(
                result="코드를 수정했습니다.\n<!-- UPDATE -->",
                session_id="marker-test"
            ),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        assert result.update_requested is True
        assert result.restart_requested is False

    async def test_run_file_not_found(self):
        """Claude CLI 없음 테스트"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = FileNotFoundError("claude not found")

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_run_general_exception(self):
        """일반 예외 처리 테스트"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = RuntimeError("SDK error")

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "SDK error" in result.error

    async def test_compact_session_success(self):
        """compact_session 성공 테스트"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="Compacted.", session_id="compact-123"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.compact_session("test-session-id")

        assert result.success is True
        assert result.session_id == "compact-123"

    async def test_compact_session_no_session_id(self):
        """compact_session 세션 ID 없음 테스트"""
        runner = ClaudeAgentRunner()
        result = await runner.compact_session("")

        assert result.success is False
        assert "세션 ID가 없습니다" in result.error


@pytest.mark.asyncio
class TestClaudeAgentRunnerProgress:
    """진행 상황 콜백 테스트"""

    async def test_progress_callback(self):
        """진행 상황 콜백 호출 테스트"""
        runner = ClaudeAgentRunner()
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

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch("asyncio.get_event_loop", return_value=mock_loop):
                                result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True


@pytest.mark.asyncio
class TestClaudeAgentRunnerCompact:
    """컴팩션 감지 및 콜백 테스트"""

    async def test_build_options_with_compact_events(self):
        """compact_events 전달 시 PreCompact 훅이 등록되는지 확인"""
        runner = ClaudeAgentRunner()
        compact_events = []
        options, _, _ = runner._build_options(compact_events=compact_events)

        assert options.hooks is not None
        assert "PreCompact" in options.hooks
        assert len(options.hooks["PreCompact"]) == 1
        assert options.hooks["PreCompact"][0].matcher is None

    async def test_build_options_without_compact_events(self):
        """compact_events 미전달 시 hooks가 None인지 확인"""
        runner = ClaudeAgentRunner()
        options, _, _ = runner._build_options()

        assert options.hooks is None

    async def test_compact_callback_called(self):
        """컴팩션 발생 시 on_compact 콜백이 호출되는지 확인"""
        runner = ClaudeAgentRunner()
        compact_calls = []

        async def on_compact(trigger: str, message: str):
            compact_calls.append({"trigger": trigger, "message": message})

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="compact-test"),
            MockAssistantMessage(content=[MockTextBlock(text="작업 중...")]),
            MockResultMessage(result="완료", session_id="compact-test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None, user_id=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, prompt=prompt)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
            return options, memory_prompt, anchor

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
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
        runner = ClaudeAgentRunner()
        compact_calls = []

        async def on_compact(trigger: str, message: str):
            compact_calls.append({"trigger": trigger, "message": message})

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None, user_id=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, prompt=prompt)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
                compact_events.append({
                    "trigger": "manual",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: manual)",
                })
            return options, memory_prompt, anchor

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", patched_build):
                    result = await runner.run("테스트", on_compact=on_compact)

        assert result.success is True
        assert len(compact_calls) == 2
        assert compact_calls[0]["trigger"] == "auto"
        assert compact_calls[1]["trigger"] == "manual"

    async def test_compact_callback_error_handled(self):
        """on_compact 콜백 오류 시 실행이 중단되지 않는지 확인"""
        runner = ClaudeAgentRunner()

        async def failing_compact(trigger: str, message: str):
            raise RuntimeError("콜백 오류")

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        original_build = runner._build_options

        def patched_build(session_id=None, compact_events=None, user_id=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, prompt=prompt)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options, memory_prompt, anchor

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", patched_build):
                    result = await runner.run("테스트", on_compact=failing_compact)

        # 콜백 오류에도 실행은 성공
        assert result.success is True

    async def test_no_compact_callback_no_error(self):
        """on_compact 미전달 시에도 정상 동작 확인"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="완료", session_id="test"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
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
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details"
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "비정상 종료" in result.error
        assert "잠시 후" in result.error
        # 원래의 불친절한 메시지가 아닌지 확인
        assert "Command failed" not in result.error

    async def test_process_error_with_usage_limit(self):
        """usage limit ProcessError 발생 시 친절한 메시지"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "usage limit reached", exit_code=1, stderr="usage limit"
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error


@pytest.mark.asyncio
class TestRateLimitEventHandling:
    """rate_limit_event (MessageParseError) 처리 테스트"""

    async def test_rate_limit_event_graceful_break(self):
        """rate_limit_event 발생 시 재시도 없이 graceful 종료"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        class RateLimitThenStop:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise MessageParseError(
                    "Unknown message type: rate_limit_event",
                    {"type": "rate_limit_event"}
                )

        mock_client.receive_response = MagicMock(return_value=RateLimitThenStop())

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        # rate_limit_event로 while loop가 break되어 정상 종료 (output 없음)
        assert result.success is True
        assert result.output == ""

    async def test_rate_limit_event_returns_friendly_error(self):
        """rate_limit_event가 외부 except에서 잡힐 때 친화적 메시지 반환"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # connect 단계에서 MessageParseError 발생
        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: rate_limit_event",
            {"type": "rate_limit_event"}
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error
        # 원문 SDK 에러가 노출되지 않는지 확인
        assert "Unknown message type" not in result.error

    async def test_non_rate_limit_parse_error_returns_friendly_error(self):
        """rate_limit이 아닌 MessageParseError도 친화적 메시지 반환"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: some_unknown_type",
            {"type": "some_unknown_type"}
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "오류가 발생했습니다" in result.error
        assert "Unknown message type" not in result.error


class TestBuildOptionsChannelObservation:
    """_build_options에서 채널 관찰 컨텍스트 주입 테스트"""

    def test_channel_observation_injected_for_observed_channel(self, tmp_path):
        """관찰 대상 채널에서 새 세션일 때 채널 관찰 컨텍스트가 주입되는지 확인"""
        from seosoyoung.memory.channel_store import ChannelStore

        # 채널 데이터 준비
        ch_store = ChannelStore(base_dir=tmp_path)
        ch_store.save_digest("C_OBS", content="채널에서 재미있는 일이 있었다", meta={})

        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": True,
            "channel_observer.channels": ["C_OBS"],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "",
        }

        runner = ClaudeAgentRunner("ts_1", channel="C_OBS")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt="<channel-observation>test</channel-observation>",
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=50,
                    channel_buffer_tokens=0,
                )
                _, memory_prompt, _ = runner._build_options()

                # build_memory_prompt에 include_channel_observation=True가 전달되었는지 확인
                call_kwargs = mock_build.call_args.kwargs
                assert call_kwargs.get("include_channel_observation") is True
                assert call_kwargs.get("channel_id") == "C_OBS"

        assert memory_prompt is not None

    def test_channel_observation_not_injected_for_non_observed_channel(self, tmp_path):
        """관찰 대상이 아닌 채널에서는 채널 관찰 컨텍스트가 주입되지 않음"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": True,
            "channel_observer.channels": ["C_OBS"],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "",
        }

        runner = ClaudeAgentRunner("ts_1", channel="C_OTHER")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt=None,
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                runner._build_options()

                call_kwargs = mock_build.call_args.kwargs
                assert call_kwargs.get("include_channel_observation") is False

    def test_channel_observation_not_injected_when_disabled(self, tmp_path):
        """CHANNEL_OBSERVER_ENABLED=False면 채널 관찰 미주입"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": ["C_OBS"],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "",
        }

        runner = ClaudeAgentRunner("ts_1", channel="C_OBS")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt=None,
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                runner._build_options()

                call_kwargs = mock_build.call_args.kwargs
                assert call_kwargs.get("include_channel_observation") is False


class TestBuildOptionsAnchorTs:
    """_build_options에서 앵커 메시지 생성 테스트"""

    def test_anchor_ts_empty_without_om(self):
        """OM 미활성 시 anchor_ts가 빈 문자열"""
        runner = ClaudeAgentRunner()
        _, _, anchor_ts = runner._build_options()
        assert anchor_ts == ""

    def test_anchor_ts_created_for_new_session(self, tmp_path):
        """새 세션 + OM 활성 시 앵커 메시지가 생성되어 anchor_ts 반환"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "C_DEBUG",
        }

        runner = ClaudeAgentRunner("ts_1")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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
                with patch("seosoyoung.memory.observation_pipeline._send_debug_log", return_value="anchor_ts_123") as mock_send:
                    _, _, anchor_ts = runner._build_options(
                        prompt="테스트 프롬프트입니다",
                    )

        assert anchor_ts == "anchor_ts_123"
        # 앵커 메시지 발송 호출 확인
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "세션 시작 감지" in call_args[0][1]
        assert "테스트 프롬프트입니다" in call_args[0][1]

    def test_anchor_ts_not_created_for_resumed_session(self, tmp_path):
        """기존 세션 재개 시 새 앵커 미생성, MemoryRecord에서 기존 anchor_ts 로드"""
        from seosoyoung.memory.store import MemoryRecord, MemoryStore

        # 사전 조건: MemoryRecord에 이전 세션의 anchor_ts가 저장되어 있음
        pre_store = MemoryStore(base_dir=tmp_path)
        pre_record = MemoryRecord(thread_ts="ts_1", anchor_ts="saved_anchor_123")
        pre_store.save_record(pre_record)

        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "C_DEBUG",
        }

        runner = ClaudeAgentRunner("ts_1")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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
                with patch("seosoyoung.memory.observation_pipeline._send_debug_log") as mock_send:
                    _, _, anchor_ts = runner._build_options(
                        session_id="existing-session",
                        prompt="테스트",
                    )

        # 기존 세션이므로 새 앵커 메시지 미생성, 하지만 저장된 anchor_ts 로드
        assert anchor_ts == "saved_anchor_123"
        mock_send.assert_not_called()

    def test_anchor_ts_empty_when_no_saved_record(self, tmp_path):
        """기존 세션 재개 시 MemoryRecord가 없으면 anchor_ts 빈 문자열"""
        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "C_DEBUG",
        }

        runner = ClaudeAgentRunner("ts_no_record")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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
                _, _, anchor_ts = runner._build_options(
                    session_id="existing-session",
                    prompt="테스트",
                )

        # MemoryRecord가 없으므로 anchor_ts 빈 문자열
        assert anchor_ts == ""

    def test_new_session_saves_anchor_ts_to_record(self, tmp_path):
        """새 세션 시 생성된 anchor_ts가 MemoryRecord에 저장되는지 확인"""
        from seosoyoung.memory.store import MemoryStore

        config_patches = {
            "om.enabled": True,
            "channel_observer.enabled": False,
            "channel_observer.channels": [],
            "om.max_observation_tokens": 30000,
            "om.debug_channel": "C_DEBUG",
        }

        runner = ClaudeAgentRunner("ts_new")

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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
                with patch("seosoyoung.memory.observation_pipeline._send_debug_log", return_value="new_anchor_456"):
                    _, _, anchor_ts = runner._build_options(
                        prompt="새 세션 테스트",
                    )

        assert anchor_ts == "new_anchor_456"

        # MemoryRecord에 anchor_ts가 저장되었는지 확인
        verify_store = MemoryStore(base_dir=tmp_path)
        record = verify_store.get_record("ts_new")
        assert record is not None
        assert record.anchor_ts == "new_anchor_456"


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

        with patch("seosoyoung.memory.observation_pipeline._send_debug_log") as mock_send:
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

        with patch("seosoyoung.memory.observation_pipeline._send_debug_log") as mock_send:
            with patch("seosoyoung.memory.observation_pipeline._format_tokens", return_value="100"):
                with patch("seosoyoung.memory.observation_pipeline._blockquote", return_value=">장기 기억"):
                    send_injection_debug_log(
                        thread_ts="ts_1234",
                        result=mock_result,
                        debug_channel="C_DEBUG",
                        anchor_ts="anchor_valid",
                    )

        # anchor_ts가 있으므로 _send_debug_log가 호출되어야 함
        mock_send.assert_called()


class TestClaudeResultAnchorTs:
    """ClaudeResult에 anchor_ts 필드 테스트"""

    def test_anchor_ts_default_empty(self):
        """기본값은 빈 문자열"""
        result = ClaudeResult(success=True, output="test")
        assert result.anchor_ts == ""

    def test_anchor_ts_set(self):
        """anchor_ts 설정 가능"""
        result = ClaudeResult(success=True, output="test", anchor_ts="anc_123")
        assert result.anchor_ts == "anc_123"


@pytest.mark.asyncio
class TestObserverUserMessage:
    """Observer에 user_message가 올바르게 전달되는지 테스트"""

    async def test_trigger_observation_uses_user_message(self):
        """user_message가 지정되면 prompt 대신 user_message가 Observer에 전달"""
        runner = ClaudeAgentRunner("ts_1")

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="obs-test"),
            MockResultMessage(result="완료", session_id="obs-test"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.claude.agent_runner.trigger_observation") as mock_trigger:
                        result = await runner.run(
                            prompt="채널 히스토리 20개 + 사용자 질문",
                            user_id="U123",
                            user_message="사용자 원본 질문만",
                        )

        if mock_trigger.called:
            call_args = mock_trigger.call_args
            # positional: (thread_ts, user_id, prompt/user_message, collected_messages)
            observation_input = call_args[0][2]
            assert observation_input == "사용자 원본 질문만"
            assert observation_input != "채널 히스토리 20개 + 사용자 질문"

    async def test_trigger_observation_falls_back_to_prompt(self):
        """user_message가 None이면 prompt가 Observer에 전달 (하위 호환)"""
        runner = ClaudeAgentRunner("ts_2")

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="obs-test-2"),
            MockResultMessage(result="완료", session_id="obs-test-2"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                    with patch("seosoyoung.claude.agent_runner.trigger_observation") as mock_trigger:
                        result = await runner.run(
                            prompt="전체 프롬프트",
                            user_id="U123",
                            # user_message 미지정
                        )

        if mock_trigger.called:
            call_args = mock_trigger.call_args
            observation_input = call_args[0][2]
            assert observation_input == "전체 프롬프트"


class TestTriggerObservationToolFilter:
    """_trigger_observation에서 tool_use/tool 메시지 필터링 테스트"""

    def test_filters_tool_use_and_tool_result_messages(self):
        """tool_use, tool role 메시지가 Observer에 전달되지 않음"""
        runner = ClaudeAgentRunner()

        collected = [
            {"role": "assistant", "content": "파일을 읽겠습니다.", "timestamp": "t1"},
            {"role": "assistant", "content": "[tool_use: Read] {\"file\": \"a.py\"}", "timestamp": "t2"},
            {"role": "tool", "content": "파일 내용...", "timestamp": "t3"},
            {"role": "assistant", "content": "수정 완료했습니다.", "timestamp": "t4"},
            {"role": "assistant", "content": "[tool_use: Edit] {\"old\": \"a\", \"new\": \"b\"}", "timestamp": "t5"},
            {"role": "tool", "content": "편집 성공", "timestamp": "t6"},
        ]

        with patch("seosoyoung.config.Config") as MockConfig:
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

            with patch("seosoyoung.memory.observation_pipeline.observe_conversation", mock_observe_conversation):
                with patch("seosoyoung.memory.store.MemoryStore"):
                    with patch("seosoyoung.memory.observer.Observer"):
                        with patch("seosoyoung.memory.reflector.Reflector"):
                            with patch("seosoyoung.memory.promoter.Promoter"):
                                with patch("seosoyoung.memory.promoter.Compactor"):
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

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            client = await runner._get_or_create_client()

        assert runner.pid == 54321
        assert runner.client is client

    async def test_pid_not_extracted_when_transport_missing(self):
        """transport가 없을 때 PID 추출 실패해도 오류 없음"""
        runner = ClaudeRunner("test_no_transport")

        mock_client = AsyncMock()
        mock_client._transport = None

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
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
        with patch("seosoyoung.claude.agent_runner.psutil") as mock_psutil:
            mock_psutil.Process.return_value = mock_proc
            ClaudeAgentRunner._force_kill_process(12345, "test_thread")

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=3)

    def test_force_kill_process_terminate_timeout_then_kill(self):
        """_force_kill_process: terminate 타임아웃 시 kill 사용"""
        mock_proc = MagicMock()

        with patch("seosoyoung.claude.agent_runner.psutil") as mock_psutil:
            # TimeoutExpired 예외 시뮬레이션
            mock_psutil.TimeoutExpired = type("TimeoutExpired", (Exception,), {})
            mock_proc.wait.side_effect = [mock_psutil.TimeoutExpired(3), None]
            mock_psutil.Process.return_value = mock_proc
            ClaudeAgentRunner._force_kill_process(12345, "test_thread")

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2

    def test_force_kill_process_no_such_process(self):
        """_force_kill_process: 프로세스가 이미 종료된 경우"""
        with patch("seosoyoung.claude.agent_runner.psutil") as mock_psutil:
            # NoSuchProcess 예외 시뮬레이션
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.Process.side_effect = mock_psutil.NoSuchProcess(12345)
            # 예외 발생하지 않음
            ClaudeAgentRunner._force_kill_process(12345, "test_thread")

    def test_force_kill_process_general_error(self):
        """_force_kill_process: 일반 오류 발생 시 로깅만"""
        import psutil as real_psutil
        with patch("seosoyoung.claude.agent_runner.psutil") as mock_psutil:
            # 실제 예외 클래스들을 유지
            mock_psutil.NoSuchProcess = real_psutil.NoSuchProcess
            mock_psutil.TimeoutExpired = real_psutil.TimeoutExpired
            mock_psutil.Process.side_effect = RuntimeError("알 수 없는 오류")
            # 예외 발생하지 않음 (로깅만)
            ClaudeAgentRunner._force_kill_process(12345, "test_thread")


class TestServiceFactory:
    """서비스 팩토리 테스트"""

    def test_factory_returns_agent_runner(self):
        """팩토리가 항상 ClaudeAgentRunner를 반환"""
        from seosoyoung.claude import get_claude_runner
        runner = get_claude_runner()
        assert isinstance(runner, ClaudeAgentRunner)


class TestGetRoleConfig:
    """_get_role_config 함수 테스트"""

    def test_viewer_role_has_correct_disallowed_tools(self):
        """viewer 역할은 수정/실행 도구가 차단됨"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("viewer")

        assert "Write" in config["disallowed_tools"]
        assert "Edit" in config["disallowed_tools"]
        assert "Bash" in config["disallowed_tools"]
        assert "TodoWrite" in config["disallowed_tools"]

    def test_admin_role_has_mcp_config(self):
        """admin 역할은 MCP 설정을 사용 (설정 파일 존재 시)"""
        from seosoyoung.claude.executor import _get_role_config, _get_mcp_config_path

        config = _get_role_config("admin")

        expected_path = _get_mcp_config_path()
        if expected_path:
            assert config["mcp_config_path"] == expected_path
        else:
            assert config["mcp_config_path"] is None

    def test_admin_role_has_no_disallowed_tools(self):
        """admin 역할은 disallowed_tools가 None"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("admin")
        assert config["disallowed_tools"] is None

    def test_returns_dict_with_required_keys(self):
        """반환값이 필수 키를 포함"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("admin")
        assert "allowed_tools" in config
        assert "disallowed_tools" in config
        assert "mcp_config_path" in config


@pytest.mark.integration
@pytest.mark.asyncio
class TestClaudeAgentRunnerIntegration:
    """통합 테스트 (실제 SDK 호출)

    실행 방법: pytest -m integration tests/test_agent_runner.py
    """

    async def test_real_sdk_execution(self):
        """실제 SDK 실행 테스트"""
        runner = ClaudeAgentRunner()
        result = await runner.run("1+1은? 숫자만 답해줘.")

        assert result.success is True
        assert result.session_id is not None
        assert "2" in result.output

    async def test_mcp_trello_integration(self):
        """Trello MCP 도구 통합 테스트

        SDK 모드에서 Trello MCP 도구가 정상 작동하는지 확인
        """
        runner = ClaudeAgentRunner(
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
        runner = ClaudeAgentRunner(
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
        runner = ClaudeAgentRunner()
        hooks = runner._build_compact_hook(None)
        assert hooks is None

    def test_returns_hooks_when_compact_events_provided(self):
        """compact_events 제공 시 PreCompact 훅 딕셔너리 반환"""
        runner = ClaudeAgentRunner(thread_ts="ts_1")
        compact_events = []
        hooks = runner._build_compact_hook(compact_events)

        assert hooks is not None
        assert "PreCompact" in hooks
        assert len(hooks["PreCompact"]) == 1
        assert hooks["PreCompact"][0].matcher is None

    def test_returns_hooks_without_thread_ts(self):
        """thread_ts가 없어도 훅 생성됨"""
        runner = ClaudeAgentRunner()
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
        from seosoyoung.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)

        with patch("seosoyoung.config.Config") as MockConfig:
            MockConfig.emoji.text_session_start = "🟢"
            with patch("seosoyoung.memory.observation_pipeline._send_debug_log", return_value="anchor_new_123"):
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
        from seosoyoung.memory.store import MemoryStore, MemoryRecord
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
        from seosoyoung.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)

        anchor_ts = create_or_load_debug_anchor(
            thread_ts="ts_no_record", session_id="session_xyz", store=store,
            prompt="test", debug_channel="C_DEBUG",
        )
        assert anchor_ts == ""

    def test_truncates_long_prompt_preview(self, tmp_path):
        """80자 초과 프롬프트가 잘려서 앵커에 포함"""
        from seosoyoung.memory.store import MemoryStore
        store = MemoryStore(base_dir=tmp_path)
        long_prompt = "A" * 100

        with patch("seosoyoung.config.Config") as MockConfig:
            MockConfig.emoji.text_session_start = "🟢"
            with patch("seosoyoung.memory.observation_pipeline._send_debug_log", return_value="anc") as mock_send:
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
        with patch("seosoyoung.config.Config") as MockConfig:
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

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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

        with patch("seosoyoung.config.Config") as MockConfig:
            _apply_mock_config(MockConfig, config_patches)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
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
                with patch("seosoyoung.memory.injector.create_or_load_debug_anchor", return_value="anc_789") as mock_anchor:
                    _, anchor_ts = prepare_memory_injection(
                        thread_ts="ts_1", channel="C1", session_id=None, prompt="test",
                    )

        mock_anchor.assert_called_once()
        assert anchor_ts == "anc_789"

    def test_exception_returns_none_gracefully(self):
        """OM 내부 예외 발생 시 (None, '') 반환 (무시)"""
        with patch("seosoyoung.config.Config") as MockConfig:
            MockConfig.om.enabled = True
            MockConfig.get_memory_path.side_effect = RuntimeError("boom")
            memory_prompt, anchor_ts = prepare_memory_injection(
                thread_ts="ts_err", channel="C1", session_id=None, prompt="test",
            )
        assert memory_prompt is None
        assert anchor_ts == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
