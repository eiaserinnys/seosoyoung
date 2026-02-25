"""rescue engine_adapter 테스트

rescue/engine_adapter.py의 create_runner, interrupt, compact_session_sync를 테스트합니다.
ClaudeRunner 내부 동작(SDK 통신, 에러 분류 등)은 tests/claude/test_agent_runner.py에서 검증하므로,
여기서는 어댑터가 올바른 설정으로 ClaudeRunner를 생성하고 위임하는지에 집중합니다.
"""

import pytest
from unittest.mock import patch, MagicMock

from seosoyoung.rescue.engine_adapter import (
    create_runner,
    interrupt,
    compact_session_sync,
    ALLOWED_TOOLS,
    DISALLOWED_TOOLS,
)


class TestCreateRunner:
    """create_runner 테스트"""

    def test_creates_claude_runner_with_thread_ts(self):
        """thread_ts가 ClaudeRunner에 전달되는지 확인"""
        runner = create_runner("1234567890.123456")
        assert runner.thread_ts == "1234567890.123456"

    def test_creates_claude_runner_without_thread_ts(self):
        """thread_ts 없이도 생성 가능"""
        runner = create_runner()
        assert runner.thread_ts == ""

    def test_runner_has_correct_tools_config(self):
        """allowed/disallowed tools가 올바르게 설정되는지 확인"""
        runner = create_runner("ts_123")
        assert runner.allowed_tools == ALLOWED_TOOLS
        assert runner.disallowed_tools == DISALLOWED_TOOLS

    def test_no_env_parameter(self):
        """ClaudeRunner에 env 파라미터를 전달하지 않는지 확인"""
        runner = create_runner("ts_123")
        # ClaudeRunner는 env 속성을 갖지 않음 (agent_runner.py에 없음)
        assert not hasattr(runner, "env")


class TestAllowedTools:
    """도구 설정 테스트"""

    def test_allowed_tools_is_none(self):
        """admin 역할의 allowed_tools=None (모든 도구 허용)"""
        assert ALLOWED_TOOLS is None

    def test_disallowed_tools_list(self):
        """금지 도구 목록이 올바른지 확인"""
        assert "WebFetch" in DISALLOWED_TOOLS
        assert "WebSearch" in DISALLOWED_TOOLS
        assert "Task" in DISALLOWED_TOOLS


class TestInterrupt:
    """interrupt 함수 테스트"""

    def test_interrupt_with_no_runner(self):
        """등록된 러너가 없으면 False 반환"""
        with patch(
            "seosoyoung.rescue.engine_adapter._get_runner", return_value=None
        ):
            assert interrupt("nonexistent_thread") is False

    def test_interrupt_with_runner(self):
        """등록된 러너가 있으면 interrupt() 호출"""
        mock_runner = MagicMock()
        mock_runner.interrupt.return_value = True

        with patch(
            "seosoyoung.rescue.engine_adapter._get_runner",
            return_value=mock_runner,
        ):
            result = interrupt("existing_thread")

        assert result is True
        mock_runner.interrupt.assert_called_once()


class TestCompactSessionSync:
    """compact_session_sync 테스트"""

    def test_compact_session_calls_runner(self):
        """compact_session_sync가 ClaudeRunner를 생성하고 compact를 위임하는지 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        mock_result = EngineResult(
            success=True, output="compacted", session_id="sess_123"
        )

        with patch(
            "seosoyoung.rescue.engine_adapter.run_in_new_loop",
            return_value=mock_result,
        ):
            result = compact_session_sync("sess_123")

        assert result.success is True
        assert result.session_id == "sess_123"
