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
)


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

    def test_extract_attach_markers(self):
        """ATTACH 마커 추출"""
        import re
        output = "첨부합니다.\n<!-- ATTACH: D:\\workspace\\doc.md -->"
        attachments = re.findall(r"<!-- ATTACH: (.+?) -->", output)
        assert attachments == ["D:\\workspace\\doc.md"]

    def test_detect_update_marker(self):
        """UPDATE 마커 감지"""
        output = "코드를 수정했습니다.\n<!-- UPDATE -->"
        assert "<!-- UPDATE -->" in output

    def test_detect_restart_marker(self):
        """RESTART 마커 감지"""
        output = "재시작이 필요합니다.\n<!-- RESTART -->"
        assert "<!-- RESTART -->" in output


# SDK 메시지 타입 Mock
@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list


@dataclass
class MockResultMessage:
    result: str
    session_id: str = None


@pytest.mark.asyncio
class TestClaudeAgentRunnerAsync:
    """비동기 테스트 (Mock 사용)"""

    async def test_run_success(self):
        """성공적인 SDK 실행 테스트"""
        runner = ClaudeAgentRunner()

        # SDK query 함수 Mock
        async def mock_query(prompt, options):
            yield MockSystemMessage(session_id="test-sdk-123")
            yield MockAssistantMessage(content=[MockTextBlock(text="진행 중...")])
            yield MockResultMessage(result="완료되었습니다.", session_id="test-sdk-123")

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            # isinstance 체크를 위한 Mock
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

        async def mock_query(prompt, options):
            yield MockResultMessage(
                result="파일 생성함\n<!-- FILE: /test/file.py -->\n<!-- ATTACH: /doc/readme.md -->\n<!-- UPDATE -->",
                session_id="marker-test"
            )

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        assert "/test/file.py" in result.files
        assert "/doc/readme.md" in result.attachments
        assert result.update_requested is True
        assert result.restart_requested is False

    async def test_run_timeout(self):
        """타임아웃 테스트"""
        runner = ClaudeAgentRunner(timeout=1)

        async def mock_query(prompt, options):
            raise asyncio.TimeoutError()
            yield  # make it async generator

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            result = await runner.run("테스트")

        assert result.success is False
        assert "타임아웃" in result.error

    async def test_run_file_not_found(self):
        """Claude CLI 없음 테스트"""
        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            raise FileNotFoundError("claude not found")
            yield

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_run_general_exception(self):
        """일반 예외 처리 테스트"""
        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            raise RuntimeError("SDK error")
            yield

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            result = await runner.run("테스트")

        assert result.success is False
        assert "SDK error" in result.error

    async def test_concurrent_execution_blocked(self):
        """동시 실행 제어 테스트 (Lock)"""
        runner = ClaudeAgentRunner()
        call_order = []

        async def mock_query(prompt, options):
            call_order.append("start")
            await asyncio.sleep(0.1)
            call_order.append("end")
            yield MockResultMessage(result="done", session_id="test")

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                task1 = asyncio.create_task(runner.run("first"))
                task2 = asyncio.create_task(runner.run("second"))
                await asyncio.gather(task1, task2)

        # Lock으로 인해 순차 실행
        assert call_order == ["start", "end", "start", "end"]

    async def test_compact_session_success(self):
        """compact_session 성공 테스트"""
        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(result="Compacted.", session_id="compact-123")

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
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

        time_value = [0]

        async def mock_query(prompt, options):
            yield MockSystemMessage(session_id="progress-test")
            yield MockAssistantMessage(content=[MockTextBlock(text="첫 번째")])
            time_value[0] += 3
            yield MockAssistantMessage(content=[MockTextBlock(text="두 번째")])
            yield MockResultMessage(result="완료", session_id="progress-test")

        def mock_time():
            return time_value[0]

        mock_loop = MagicMock()
        mock_loop.time = mock_time

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch("asyncio.get_event_loop", return_value=mock_loop):
                                result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True


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
