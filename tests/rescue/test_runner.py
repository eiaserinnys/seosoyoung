"""Phase 1 테스트: runner.py (RescueRunner)"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from claude_code_sdk._errors import MessageParseError

from seosoyoung.rescue.runner import (
    RescueRunner,
    RescueResult,
    _classify_process_error,
    ALLOWED_TOOLS,
    DISALLOWED_TOOLS,
)


# MCP 슬랙 도구 목록 (허용 대상)
SLACK_MCP_TOOLS = [
    "mcp__seosoyoung-attach__slack_attach_file",
    "mcp__seosoyoung-attach__slack_post_message",
    "mcp__seosoyoung-attach__slack_download_thread_files",
    "mcp__seosoyoung-attach__slack_generate_image",
]



class TestBuildOptions:
    """_build_options 테스트"""

    def test_build_options_basic(self):
        """기본 옵션 생성 확인 (allowed_tools, disallowed_tools, permission_mode)"""
        runner = RescueRunner()
        options, stderr_file = runner._build_options()

        assert options.permission_mode == "bypassPermissions"
        assert options.allowed_tools is not None
        assert options.disallowed_tools is not None
        assert "Read" in options.allowed_tools
        assert "WebFetch" in options.disallowed_tools

        if stderr_file is not None:
            stderr_file.close()

    def test_build_options_with_env(self):
        """channel/thread_ts 전달 시 env에 SLACK_CHANNEL/SLACK_THREAD_TS 주입 확인"""
        runner = RescueRunner()
        options, stderr_file = runner._build_options(
            channel="C12345", thread_ts="1234567890.123456"
        )

        assert options.env is not None
        assert options.env.get("SLACK_CHANNEL") == "C12345"
        assert options.env.get("SLACK_THREAD_TS") == "1234567890.123456"

        if stderr_file is not None:
            stderr_file.close()

    def test_build_options_with_resume(self):
        """session_id 전달 시 options.resume 설정 확인"""
        runner = RescueRunner()
        options, stderr_file = runner._build_options(session_id="test-session-id-123")

        assert options.resume == "test-session-id-123"

        if stderr_file is not None:
            stderr_file.close()

    def test_build_options_without_resume(self):
        """session_id 미전달 시 resume 없음"""
        runner = RescueRunner()
        options, stderr_file = runner._build_options()

        assert not options.resume

        if stderr_file is not None:
            stderr_file.close()

    def test_build_options_allowed_tools_includes_slack_mcp(self):
        """슬랙 MCP 도구가 allowed_tools에 포함되는지 확인"""
        for tool in SLACK_MCP_TOOLS:
            assert tool in ALLOWED_TOOLS, f"{tool} should be in ALLOWED_TOOLS"

    def test_build_options_excludes_npc_tools(self):
        """NPC 도구가 allowed_tools에 없는지 확인 (eb-lore MCP로 이동됨)"""
        assert not any("npc_" in t for t in ALLOWED_TOOLS)


class TestClassifyProcessError:
    """_classify_process_error 테스트"""

    def _make_process_error(self, exit_code=1, stderr="", message=""):
        """ProcessError mock 생성"""
        err = MagicMock()
        err.exit_code = exit_code
        err.stderr = stderr
        err.__str__ = lambda self: message
        return err

    def test_classify_process_error_rate_limit(self):
        """rate limit 패턴 분류"""
        err = self._make_process_error(stderr="rate limit exceeded")
        result = _classify_process_error(err)
        assert "사용량 제한" in result

    def test_classify_process_error_auth(self):
        """인증 에러 분류"""
        err = self._make_process_error(stderr="unauthorized access")
        result = _classify_process_error(err)
        assert "인증" in result

    def test_classify_process_error_network(self):
        """네트워크 에러 분류"""
        err = self._make_process_error(stderr="connection timeout")
        result = _classify_process_error(err)
        assert "네트워크" in result

    def test_classify_process_error_exit_1(self):
        """exit code 1 기본 메시지"""
        err = self._make_process_error(exit_code=1, stderr="unknown error")
        result = _classify_process_error(err)
        assert "비정상 종료" in result


@pytest.mark.asyncio
class TestRescueRateLimitEventHandling:
    """RescueRunner rate_limit_event 스트림 처리 테스트"""

    async def test_allowed_warning_continues(self):
        """allowed_warning status는 break하지 않고 continue"""
        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        call_count = 0

        class WarningThenStop:
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

        mock_client.receive_response = MagicMock(return_value=WarningThenStop())

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is True
        assert call_count == 2

    async def test_blocked_status_breaks(self):
        """blocked status는 break하여 종료"""
        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        class BlockedEvent:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise MessageParseError(
                    "Unknown message type: rate_limit_event",
                    {
                        "type": "rate_limit_event",
                        "rate_limit_info": {
                            "status": "blocked",
                            "rateLimitType": "seven_day",
                            "utilization": 1.0,
                        },
                    },
                )

        mock_client.receive_response = MagicMock(return_value=BlockedEvent())

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is True
        assert result.output == ""
