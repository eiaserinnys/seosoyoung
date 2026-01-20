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

    def test_parse_output_attach_markers(self):
        """ATTACH 마커 추출 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "파일을 첨부합니다.\n<!-- ATTACH: D:\\workspace\\file1.md -->\n<!-- ATTACH: D:\\workspace\\file2.png -->"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert "D:\\workspace\\file1.md" in result.attachments
        assert "D:\\workspace\\file2.png" in result.attachments
        assert len(result.attachments) == 2

    def test_parse_output_mixed_markers(self):
        """FILE과 ATTACH 마커 혼합 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "<!-- FILE: /created/file.py -->\n파일을 첨부합니다.\n<!-- ATTACH: /attach/doc.md -->"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert len(result.files) == 1
        assert "/created/file.py" in result.files
        assert len(result.attachments) == 1
        assert "/attach/doc.md" in result.attachments

    def test_parse_output_update_marker(self):
        """UPDATE 마커 감지 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "코드를 수정했습니다.\n<!-- UPDATE -->"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert result.update_requested is True
        assert result.restart_requested is False

    def test_parse_output_restart_marker(self):
        """RESTART 마커 감지 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "재시작이 필요합니다.\n<!-- RESTART -->"}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert result.update_requested is False
        assert result.restart_requested is True

    def test_parse_output_no_restart_marker(self):
        """재기동 마커 없음 테스트"""
        runner = ClaudeRunner()

        lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "일반 응답입니다."}
                    ]
                }
            }),
        ]
        stdout = "\n".join(lines)

        result = runner._parse_output(stdout, "")

        assert result.update_requested is False
        assert result.restart_requested is False

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


    async def test_run_general_exception(self):
        """일반 예외 처리 테스트"""
        runner = ClaudeRunner()

        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("Unknown error")):
            result = await runner.run("테스트")

        assert result.success is False
        assert "Unknown error" in result.error


@pytest.mark.asyncio
class TestClaudeRunnerStreaming:
    """스트리밍 모드 테스트"""

    async def test_streaming_success(self):
        """스트리밍 성공 테스트"""
        runner = ClaudeRunner()
        progress_calls = []

        async def on_progress(text):
            progress_calls.append(text)

        # 스트리밍 출력 시뮬레이션
        lines = [
            json.dumps({"type": "system", "subtype": "init", "session_id": "stream-123"}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "첫 번째 응답"}]}}),
            json.dumps({"type": "result", "result": "완료"}),
        ]

        line_index = 0

        async def mock_readline():
            nonlocal line_index
            if line_index < len(lines):
                result = (lines[line_index] + "\n").encode()
                line_index += 1
                return result
            return b""

        mock_stdout = AsyncMock()
        mock_stdout.readline = mock_readline

        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True
        assert result.session_id == "stream-123"
        # 최종 출력은 result만 포함 (assistant 응답은 진행 상황으로만 표시)
        assert result.output == "완료"

    async def test_streaming_timeout(self):
        """스트리밍 타임아웃 테스트"""
        runner = ClaudeRunner(timeout=1, )

        async def on_progress(text):
            pass

        async def mock_readline():
            raise asyncio.TimeoutError()

        mock_stdout = AsyncMock()
        mock_stdout.readline = mock_readline

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is False
        assert "타임아웃" in result.error

    async def test_streaming_json_parse_error(self):
        """스트리밍 중 JSON 파싱 오류 처리 테스트"""
        runner = ClaudeRunner()

        async def on_progress(text):
            pass

        lines = [
            "이건 JSON이 아님",
            json.dumps({"type": "result", "result": "완료"}),
        ]
        line_index = 0

        async def mock_readline():
            nonlocal line_index
            if line_index < len(lines):
                result = (lines[line_index] + "\n").encode()
                line_index += 1
                return result
            return b""

        mock_stdout = AsyncMock()
        mock_stdout.readline = mock_readline

        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True
        # JSON이 아닌 라인은 무시되고 result만 반환
        assert result.output == "완료"

    async def test_streaming_progress_callback(self):
        """진행 상황 콜백 호출 테스트"""
        runner = ClaudeRunner()
        progress_calls = []

        async def on_progress(text):
            progress_calls.append(text)

        # 시간 간격을 조작하여 콜백이 호출되도록 함
        lines = [
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "A" * 100}]}}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "B" * 100}]}}),
            json.dumps({"type": "result", "result": "완료"}),
        ]
        line_index = 0
        time_value = [0]

        async def mock_readline():
            nonlocal line_index
            if line_index < len(lines):
                result = (lines[line_index] + "\n").encode()
                line_index += 1
                time_value[0] += 3  # 3초씩 증가 (progress_interval=2초 보다 큼)
                return result
            return b""

        mock_stdout = AsyncMock()
        mock_stdout.readline = mock_readline

        mock_stderr = AsyncMock()
        mock_stderr.read = AsyncMock(return_value=b"")

        mock_process = AsyncMock()
        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.wait = AsyncMock()

        def mock_time():
            return time_value[0]

        mock_loop = MagicMock()
        mock_loop.time = mock_time

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.get_event_loop", return_value=mock_loop):
                result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is True
        # 시간 간격이 충분하면 콜백이 호출됨
        assert len(progress_calls) > 0

    async def test_streaming_file_not_found(self):
        """스트리밍 모드 FileNotFoundError 테스트"""
        runner = ClaudeRunner()

        async def on_progress(text):
            pass

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_streaming_general_exception(self):
        """스트리밍 모드 일반 예외 처리 테스트"""
        runner = ClaudeRunner()

        async def on_progress(text):
            pass

        with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("Streaming error")):
            result = await runner.run("테스트", on_progress=on_progress)

        assert result.success is False
        assert "Streaming error" in result.error


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
