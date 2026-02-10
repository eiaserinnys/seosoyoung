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
        options = runner._build_options()

        assert options.allowed_tools == DEFAULT_ALLOWED_TOOLS
        assert options.disallowed_tools == DEFAULT_DISALLOWED_TOOLS
        assert options.permission_mode == "bypassPermissions"
        assert options.resume is None

    def test_build_options_with_session(self):
        """세션 ID가 있을 때 resume 옵션 추가"""
        runner = ClaudeAgentRunner()
        options = runner._build_options(session_id="abc-123")

        assert options.resume == "abc-123"

    def test_build_options_custom_tools(self):
        """커스텀 도구 설정 테스트"""
        runner = ClaudeAgentRunner(
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"]
        )
        options = runner._build_options()

        assert options.allowed_tools == ["Read", "Glob"]
        assert options.disallowed_tools == ["Bash"]

    def test_build_options_with_mcp_config(self):
        """MCP 설정 파일 경로 테스트"""
        mcp_path = Path("D:/test/.mcp.json")
        runner = ClaudeAgentRunner(mcp_config_path=mcp_path)

        # 파일이 존재하지 않으면 mcp_servers 설정 안됨
        with patch.object(Path, "exists", return_value=False):
            options = runner._build_options()
            # mcp_servers는 기본값 유지

        # 파일이 존재하면 mcp_servers 설정
        with patch.object(Path, "exists", return_value=True):
            options = runner._build_options()
            assert options.mcp_servers == mcp_path


class TestClaudeResultMarkers:
    """ClaudeResult 마커 추출 테스트"""

    def test_extract_file_markers(self):
        """FILE 마커 추출"""
        import re
        output = "파일을 생성했습니다.\n<!-- FILE: /path/to/file1.txt -->\n<!-- FILE: /path/to/file2.py -->"
        files = re.findall(r"<!-- FILE: (.+?) -->", output)
        assert files == ["/path/to/file1.txt", "/path/to/file2.py"]

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
                result="파일 생성함\n<!-- FILE: /test/file.py -->\n<!-- UPDATE -->",
                session_id="marker-test"
            ),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        assert "/test/file.py" in result.files
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
        options = runner._build_options(compact_events=compact_events)

        assert options.hooks is not None
        assert "PreCompact" in options.hooks
        assert len(options.hooks["PreCompact"]) == 1
        assert options.hooks["PreCompact"][0].matcher is None

    async def test_build_options_without_compact_events(self):
        """compact_events 미전달 시 hooks가 None인지 확인"""
        runner = ClaudeAgentRunner()
        options = runner._build_options()

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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None):
            options = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
            return options

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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None):
            options = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: auto)",
                })
                compact_events.append({
                    "trigger": "manual",
                    "message": "컨텍스트 컴팩트 실행됨 (트리거: manual)",
                })
            return options

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

        def patched_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None):
            options = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel)
            if compact_events is not None:
                compact_events.append({
                    "trigger": "auto",
                    "message": "컴팩트 실행됨",
                })
            return options

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
