"""Claude Code Runner 테스트"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.claude.runner import ClaudeRunner, ClaudeResult, SENSITIVE_ENV_KEYS


class TestClaudeRunnerUnit:
    """유닛 테스트 (Mock 사용)"""

    def test_get_filtered_env(self):
        """민감 정보가 필터링되는지 확인"""
        runner = ClaudeRunner()

        # 테스트용 환경 변수 설정
        with patch.dict(os.environ, {
            "SLACK_BOT_TOKEN": "xoxb-secret",
            "SLACK_APP_TOKEN": "xapp-secret",
            "ANTHROPIC_API_KEY": "sk-ant-secret",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        }, clear=True):
            filtered = runner._get_filtered_env()

            # 민감 정보는 제외되어야 함
            assert "SLACK_BOT_TOKEN" not in filtered
            assert "SLACK_APP_TOKEN" not in filtered
            assert "ANTHROPIC_API_KEY" not in filtered

            # 일반 환경 변수는 포함되어야 함
            assert filtered.get("PATH") == "/usr/bin"
            assert filtered.get("HOME") == "/home/user"

    def test_build_command_basic(self):
        """기본 명령어 구성 테스트"""
        runner = ClaudeRunner()
        cmd = runner._build_command("Hello Claude")

        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "Hello Claude" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "--verbose" in cmd

    def test_build_command_with_session(self):
        """세션 ID가 있을 때 --resume 옵션 추가"""
        runner = ClaudeRunner()
        cmd = runner._build_command("Hello", session_id="abc-123")

        assert "--resume" in cmd
        assert "abc-123" in cmd

    def test_build_command_without_session(self):
        """세션 ID가 없을 때 --resume 옵션 없음"""
        runner = ClaudeRunner()
        cmd = runner._build_command("Hello", session_id=None)

        assert "--resume" not in cmd

    def test_parse_output_session_id(self):
        """세션 ID 파싱 테스트"""
        runner = ClaudeRunner()

        stdout = json.dumps({
            "type": "system",
            "subtype": "init",
            "session_id": "session-abc-123"
        })

        result = runner._parse_output(stdout, "")

        assert result.session_id == "session-abc-123"
        assert result.success is True

    def test_parse_output_assistant_message(self):
        """assistant 메시지 파싱 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "system",
                "subtype": "init",
                "session_id": "test-session"
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Hello, "},
                        {"type": "text", "text": "World!"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert "Hello, " in result.output
        assert "World!" in result.output
        assert result.session_id == "test-session"

    def test_parse_output_result_message(self):
        """result 메시지 파싱 테스트"""
        runner = ClaudeRunner()

        stdout = json.dumps({
            "type": "result",
            "result": "작업이 완료되었습니다."
        })

        result = runner._parse_output(stdout, "")

        assert "작업이 완료되었습니다." in result.output

    def test_parse_output_file_markers(self):
        """FILE 마커 추출 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "파일을 생성했습니다.\n<!-- FILE: /path/to/file1.txt -->\n<!-- FILE: /path/to/file2.py -->"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert "/path/to/file1.txt" in result.files
        assert "/path/to/file2.py" in result.files
        assert len(result.files) == 2

    def test_parse_output_invalid_json(self):
        """유효하지 않은 JSON 처리"""
        runner = ClaudeRunner()

        stdout = "이것은 JSON이 아닙니다\n{invalid json}\n일반 텍스트"

        result = runner._parse_output(stdout, "")

        # JSON 파싱 실패해도 에러 없이 처리
        assert result.success is True
        assert "이것은 JSON이 아닙니다" in result.output


@pytest.mark.asyncio
class TestClaudeRunnerAsync:
    """비동기 테스트 (Mock 사용)"""

    async def test_run_success(self):
        """성공적인 실행 테스트"""
        runner = ClaudeRunner()

        mock_stdout = "\n".join([
            json.dumps({"type": "system", "subtype": "init", "session_id": "test-123"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "응답입니다"}]}}),
        ])

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(mock_stdout.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run("테스트 프롬프트")

        assert result.success is True
        assert result.session_id == "test-123"
        assert "응답입니다" in result.output

    async def test_run_timeout(self):
        """타임아웃 테스트"""
        runner = ClaudeRunner(timeout=1)  # 1초 타임아웃

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run("테스트")

        assert result.success is False
        assert "타임아웃" in result.error

    async def test_run_command_not_found(self):
        """claude 명령어 없음 테스트"""
        runner = ClaudeRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_concurrent_execution_blocked(self):
        """동시 실행 제어 테스트 (Lock)"""
        runner = ClaudeRunner()

        call_order = []

        async def slow_communicate():
            call_order.append("start")
            await asyncio.sleep(0.1)
            call_order.append("end")
            return (b'{"type": "result", "result": "done"}', b"")

        mock_process = AsyncMock()
        mock_process.communicate = slow_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # 동시에 두 개 실행
            task1 = asyncio.create_task(runner.run("first"))
            task2 = asyncio.create_task(runner.run("second"))

            await asyncio.gather(task1, task2)

        # Lock으로 인해 순차 실행되어야 함
        # start, end, start, end 순서
        assert call_order == ["start", "end", "start", "end"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestClaudeRunnerIntegration:
    """통합 테스트 (실제 Claude Code 호출)

    실행 방법: pytest -m integration tests/test_runner.py
    """

    async def test_real_execution(self):
        """실제 Claude Code 실행 테스트"""
        runner = ClaudeRunner()
        result = await runner.run("1+1은? 숫자만 답해줘.")

        assert result.success is True
        assert result.session_id is not None
        # 응답에 "2"가 포함되어야 함
        assert "2" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
