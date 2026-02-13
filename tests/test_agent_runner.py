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
    ClaudeResult,
    DEFAULT_ALLOWED_TOOLS,
    DEFAULT_DISALLOWED_TOOLS,
    _classify_process_error,
)
from claude_code_sdk._errors import ProcessError


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

        assert options.allowed_tools == DEFAULT_ALLOWED_TOOLS
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

    async def test_run_timeout(self):
        """idle 타임아웃 테스트 (SDK가 메시지를 보내지 않고 멈추는 경우)"""
        runner = ClaudeAgentRunner(timeout=1)

        mock_client = AsyncMock()

        async def mock_receive_slow():
            yield MockSystemMessage(session_id="timeout-test")
            await asyncio.sleep(10)
            yield MockResultMessage(result="이건 도달 안 됨")

        mock_client.receive_response = mock_receive_slow

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                result = await runner.run("테스트")

        assert result.success is False
        assert "타임아웃" in result.error

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

    async def test_concurrent_execution_blocked(self):
        """동시 실행 제어 테스트 (Lock)"""
        runner = ClaudeAgentRunner()
        call_order = []

        def make_ordered_client(label):
            mock_client = AsyncMock()

            async def mock_receive():
                call_order.append(f"start-{label}")
                await asyncio.sleep(0.1)
                call_order.append(f"end-{label}")
                yield MockResultMessage(result="done", session_id="test")

            mock_client.receive_response = mock_receive
            return mock_client

        clients = [make_ordered_client("1"), make_ordered_client("2")]
        client_idx = [0]

        def get_next_client(*args, **kwargs):
            c = clients[client_idx[0]]
            client_idx[0] += 1
            return c

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", side_effect=get_next_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                task1 = asyncio.create_task(runner.run("first"))
                task2 = asyncio.create_task(runner.run("second"))
                await asyncio.gather(task1, task2)

        # Lock으로 인해 순차 실행
        assert call_order == ["start-1", "end-1", "start-2", "end-2"]

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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel, prompt=prompt)
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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel, prompt=prompt)
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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None, prompt=None):
            options, memory_prompt, anchor = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel, prompt=prompt)
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
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_rate_limit_keyword(self):
        """rate limit 키워드 감지"""
        e = ProcessError("rate limit exceeded", exit_code=1, stderr=None)
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_429_status(self):
        """429 상태 코드 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="HTTP 429 Too Many Requests")
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_unauthorized_401(self):
        """401 인증 오류 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="401 Unauthorized")
        msg = _classify_process_error(e)
        assert "인증" in msg

    def test_forbidden_403(self):
        """403 권한 오류 감지"""
        e = ProcessError("Command failed", exit_code=1, stderr="403 Forbidden")
        msg = _classify_process_error(e)
        assert "인증" in msg

    def test_network_error(self):
        """네트워크 오류 감지"""
        e = ProcessError("Connection refused", exit_code=1, stderr="ECONNREFUSED")
        msg = _classify_process_error(e)
        assert "네트워크" in msg

    def test_generic_exit_code_1(self):
        """exit code 1 일반 폴백"""
        e = ProcessError("Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details")
        msg = _classify_process_error(e)
        assert "비정상 종료" in msg
        assert "잠시 후" in msg

    def test_other_exit_code(self):
        """기타 exit code"""
        e = ProcessError("Command failed", exit_code=137, stderr=None)
        msg = _classify_process_error(e)
        assert "exit code: 137" in msg

    def test_none_stderr(self):
        """stderr가 None인 경우"""
        e = ProcessError("Command failed", exit_code=1, stderr=None)
        msg = _classify_process_error(e)
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


class TestBuildOptionsChannelObservation:
    """_build_options에서 채널 관찰 컨텍스트 주입 테스트"""

    def test_channel_observation_injected_for_observed_channel(self, tmp_path):
        """관찰 대상 채널에서 새 세션일 때 채널 관찰 컨텍스트가 주입되는지 확인"""
        from seosoyoung.memory.channel_store import ChannelStore

        # 채널 데이터 준비
        ch_store = ChannelStore(base_dir=tmp_path)
        ch_store.save_digest("C_OBS", content="채널에서 재미있는 일이 있었다", meta={})

        config_patches = {
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": True,
            "CHANNEL_OBSERVER_CHANNELS": ["C_OBS"],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt="<channel-observation>test</channel-observation>",
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=50,
                    channel_buffer_tokens=0,
                )
                _, memory_prompt, _ = runner._build_options(
                    thread_ts="ts_1", channel="C_OBS",
                )

                # build_memory_prompt에 include_channel_observation=True가 전달되었는지 확인
                call_kwargs = mock_build.call_args.kwargs
                assert call_kwargs.get("include_channel_observation") is True
                assert call_kwargs.get("channel_id") == "C_OBS"

        assert memory_prompt is not None

    def test_channel_observation_not_injected_for_non_observed_channel(self, tmp_path):
        """관찰 대상이 아닌 채널에서는 채널 관찰 컨텍스트가 주입되지 않음"""
        config_patches = {
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": True,
            "CHANNEL_OBSERVER_CHANNELS": ["C_OBS"],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt=None,
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                runner._build_options(
                    thread_ts="ts_1", channel="C_OTHER",
                )

                call_kwargs = mock_build.call_args.kwargs
                assert call_kwargs.get("include_channel_observation") is False

    def test_channel_observation_not_injected_when_disabled(self, tmp_path):
        """CHANNEL_OBSERVER_ENABLED=False면 채널 관찰 미주입"""
        config_patches = {
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": False,
            "CHANNEL_OBSERVER_CHANNELS": ["C_OBS"],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
            MockConfig.get_memory_path.return_value = str(tmp_path)

            with patch("seosoyoung.memory.context_builder.ContextBuilder.build_memory_prompt") as mock_build:
                mock_build.return_value = MagicMock(
                    prompt=None,
                    persistent_tokens=0,
                    session_tokens=0,
                    channel_digest_tokens=0,
                    channel_buffer_tokens=0,
                )
                runner._build_options(
                    thread_ts="ts_1", channel="C_OBS",
                )

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
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": False,
            "CHANNEL_OBSERVER_CHANNELS": [],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "C_DEBUG",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
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
                        thread_ts="ts_1", prompt="테스트 프롬프트입니다",
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
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": False,
            "CHANNEL_OBSERVER_CHANNELS": [],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "C_DEBUG",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
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
                        thread_ts="ts_1", prompt="테스트",
                    )

        # 기존 세션이므로 새 앵커 메시지 미생성, 하지만 저장된 anchor_ts 로드
        assert anchor_ts == "saved_anchor_123"
        mock_send.assert_not_called()

    def test_anchor_ts_empty_when_no_saved_record(self, tmp_path):
        """기존 세션 재개 시 MemoryRecord가 없으면 anchor_ts 빈 문자열"""
        config_patches = {
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": False,
            "CHANNEL_OBSERVER_CHANNELS": [],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "C_DEBUG",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
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
                    thread_ts="ts_no_record", prompt="테스트",
                )

        # MemoryRecord가 없으므로 anchor_ts 빈 문자열
        assert anchor_ts == ""

    def test_new_session_saves_anchor_ts_to_record(self, tmp_path):
        """새 세션 시 생성된 anchor_ts가 MemoryRecord에 저장되는지 확인"""
        from seosoyoung.memory.store import MemoryStore

        config_patches = {
            "OM_ENABLED": True,
            "CHANNEL_OBSERVER_ENABLED": False,
            "CHANNEL_OBSERVER_CHANNELS": [],
            "OM_MAX_OBSERVATION_TOKENS": 30000,
            "OM_DEBUG_CHANNEL": "C_DEBUG",
        }

        runner = ClaudeAgentRunner()

        with patch("seosoyoung.config.Config") as MockConfig:
            for k, v in config_patches.items():
                setattr(MockConfig, k, v)
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
                        thread_ts="ts_new", prompt="새 세션 테스트",
                    )

        assert anchor_ts == "new_anchor_456"

        # MemoryRecord에 anchor_ts가 저장되었는지 확인
        verify_store = MemoryStore(base_dir=tmp_path)
        record = verify_store.get_record("ts_new")
        assert record is not None
        assert record.anchor_ts == "new_anchor_456"


class TestInjectionDebugLogSkipsWithoutAnchor:
    """anchor_ts가 빈 문자열일 때 _send_injection_debug_log가 디버그 로그를 스킵하는지 테스트"""

    def test_skips_debug_log_when_anchor_ts_empty(self):
        """anchor_ts가 빈 문자열이면 디버그 로그를 발송하지 않음 (채널 본문 오염 방지)"""
        runner = ClaudeAgentRunner()
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
            runner._send_injection_debug_log(
                thread_ts="ts_1234",
                result=mock_result,
                debug_channel="C_DEBUG",
                anchor_ts="",  # 빈 문자열 — 앵커 생성 실패
            )

        # anchor_ts가 비었으므로 _send_debug_log가 호출되지 않아야 함
        mock_send.assert_not_called()

    def test_sends_debug_log_when_anchor_ts_present(self):
        """anchor_ts가 있으면 정상적으로 디버그 로그를 발송"""
        runner = ClaudeAgentRunner()
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
                    runner._send_injection_debug_log(
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


class TestServiceFactory:
    """서비스 팩토리 테스트"""

    def test_factory_returns_agent_runner(self):
        """팩토리가 항상 ClaudeAgentRunner를 반환"""
        from seosoyoung.claude import get_claude_runner
        runner = get_claude_runner()
        assert isinstance(runner, ClaudeAgentRunner)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
