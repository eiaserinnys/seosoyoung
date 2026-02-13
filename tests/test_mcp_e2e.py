"""MCP 파일 첨부 E2E 통합 테스트

Phase 4: 전체 파이프라인 검증
- 멘션 → attach_file MCP 호출 → 슬랙 파일 첨부
- 트렐로 모드에서 첨부 파일 정상 전달
- 에러 케이스 (파일 없음, workspace 외부, 크기 초과)
- MCP 서버 독립 구동 (도구 등록, stdio 프로토콜)
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestMCPServerStandalone:
    """MCP 서버 독립 구동 테스트"""

    def test_server_instance_creation(self):
        """FastMCP 서버 인스턴스가 정상 생성됨"""
        from seosoyoung.mcp.server import mcp

        assert mcp.name == "seosoyoung-attach"

    def test_server_has_five_tools(self):
        """서버에 5개 도구가 등록됨"""
        from seosoyoung.mcp.server import mcp

        tools = list(mcp._tool_manager._tools.keys())
        assert "slack_attach_file" in tools
        assert "slack_get_context" in tools
        assert "slack_post_message" in tools
        assert "slack_generate_image" in tools
        assert "slack_download_thread_files" in tools
        assert len(tools) == 5

    def test_get_context_reads_env(self):
        """slack_get_context가 환경변수에서 값을 읽음"""
        with patch.dict(os.environ, {
            "SLACK_CHANNEL": "C_E2E_TEST",
            "SLACK_THREAD_TS": "9999999999.000001",
        }):
            from seosoyoung.mcp.tools.attach import get_slack_context

            result = get_slack_context()
            assert result["channel"] == "C_E2E_TEST"
            assert result["thread_ts"] == "9999999999.000001"


class TestMCPE2EMentionFlow:
    """멘션 → attach_file MCP 호출 → 슬랙 파일 첨부 E2E"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"E2E test file"):
        """workspace 내부에 테스트 파일 생성"""
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_full_attach_flow(self, mock_get_client):
        """전체 파일 첨부 플로우: 파일 생성 → MCP 도구 호출 → 슬랙 업로드"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(suffix=".md", content=b"# Test Report")
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000001",
            )

            assert result["success"] is True
            assert "첨부 완료" in result["message"]

            # Slack API 호출 검증
            mock_client.files_upload_v2.assert_called_once()
            call_kwargs = mock_client.files_upload_v2.call_args
            assert call_kwargs.kwargs["channel"] == "C_E2E_CHANNEL"
            assert call_kwargs.kwargs["thread_ts"] == "1111111111.000001"
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_yaml_file(self, mock_get_client):
        """YAML 파일 첨부 (대사 데이터 내보내기 시나리오)"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(
            suffix=".yaml",
            content=b"dialogues:\n  - id: test\n    text: hello",
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000002",
            )

            assert result["success"] is True
            mock_client.files_upload_v2.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_xlsx_file(self, mock_get_client):
        """Excel 파일 첨부 (대사 엑셀 내보내기 시나리오)"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(
            suffix=".xlsx", content=b"PK\x03\x04fake-xlsx-content"
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000003",
            )

            assert result["success"] is True
        finally:
            os.unlink(tmp_path)


class TestMCPE2ETrelloFlow:
    """트렐로 모드에서 첨부 파일 정상 전달 E2E"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"trello test"):
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_runner_env_injection_for_trello(self):
        """트렐로 모드: _build_options에서 SLACK_CHANNEL/THREAD_TS가 env에 주입됨"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()
        options, _memory_prompt, _anchor_ts = runner._build_options(
            channel="C_TRELLO_NOTIFY",
            thread_ts="2222222222.000001",
        )

        assert options.env["SLACK_CHANNEL"] == "C_TRELLO_NOTIFY"
        assert options.env["SLACK_THREAD_TS"] == "2222222222.000001"

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_in_trello_thread(self, mock_get_client):
        """트렐로 스레드에서 파일 첨부"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(suffix=".json", content=b'{"result": "ok"}')
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_TRELLO_NOTIFY",
                thread_ts="2222222222.000001",
            )

            assert result["success"] is True
            call_kwargs = mock_client.files_upload_v2.call_args
            assert call_kwargs.kwargs["channel"] == "C_TRELLO_NOTIFY"
            assert call_kwargs.kwargs["thread_ts"] == "2222222222.000001"
        finally:
            os.unlink(tmp_path)

    def test_admin_runner_has_mcp_for_trello(self):
        """admin 역할 runner에 MCP 설정이 있어 트렐로 모드에서도 첨부 가능"""
        from seosoyoung.claude.executor import get_runner_for_role

        runner = get_runner_for_role("admin")
        assert runner.mcp_config_path is not None
        assert "mcp__seosoyoung-attach__slack_attach_file" in runner.allowed_tools


class TestMCPE2EErrorCases:
    """E2E 에러 케이스 테스트"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"test"):
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_file_not_found_returns_error(self):
        """존재하지 않는 파일 → success=False"""
        from seosoyoung.mcp.tools.attach import attach_file

        result = attach_file(
            file_path="/absolutely/nonexistent/file.txt",
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is False
        assert "존재하지 않" in result["message"]

    def test_workspace_outside_file_rejected(self):
        """workspace 외부 파일 → success=False"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"outside workspace")
            outside_path = tmp.name

        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=outside_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "workspace" in result["message"].lower() or "허용" in result["message"]
        finally:
            os.unlink(outside_path)

    def test_disallowed_extension_rejected(self):
        """허용되지 않는 확장자(.exe) → success=False"""
        tmp_path = self._make_workspace_file(suffix=".exe", content=b"MZ")
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "확장자" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_size_exceeded_rejected(self):
        """20MB 초과 파일 → success=False"""
        tmp_path = self._make_workspace_file(
            content=b"x" * (20 * 1024 * 1024 + 1)
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "크기" in result["message"] or "20MB" in result["message"]
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_slack_api_failure_handled(self, mock_get_client):
        """Slack API 에러 → success=False, 에러 메시지 포함"""
        mock_client = MagicMock()
        mock_client.files_upload_v2.side_effect = Exception("channel_not_found")
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file()
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_INVALID",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "channel_not_found" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_directory_path_rejected(self):
        """디렉토리 경로를 지정하면 거부"""
        dir_path = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        dir_path.mkdir(parents=True, exist_ok=True)

        from seosoyoung.mcp.tools.attach import attach_file

        result = attach_file(
            file_path=str(dir_path),
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is False
        assert "파일이 아님" in result["message"]


class TestMCPConfigIntegrity:
    """mcp_config.json과 봇 설정 정합성 E2E"""

    def test_mcp_config_server_name_matches(self):
        """mcp_config.json의 서버 이름이 FastMCP 서버와 일치"""
        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        from seosoyoung.mcp.server import mcp

        assert "seosoyoung-attach" in config
        assert mcp.name == "seosoyoung-attach"

    def test_allowed_tools_match_mcp_tool_names(self):
        """ROLE_TOOLS의 MCP 도구 패턴이 실제 도구 이름과 일치"""
        from seosoyoung.config import Config
        from seosoyoung.mcp.server import mcp

        admin_mcp_tools = [
            t for t in Config.ROLE_TOOLS["admin"]
            if t.startswith("mcp__seosoyoung-attach__")
        ]

        actual_tools = list(mcp._tool_manager._tools.keys())

        for tool_pattern in admin_mcp_tools:
            # mcp__seosoyoung-attach__slack_attach_file → slack_attach_file
            tool_name = tool_pattern.split("__")[-1]
            assert tool_name in actual_tools, f"{tool_name} not in MCP server tools"

    def test_default_allowed_tools_include_all_mcp_tools(self):
        """DEFAULT_ALLOWED_TOOLS에 MCP 도구 5개 모두 포함"""
        from seosoyoung.claude.agent_runner import DEFAULT_ALLOWED_TOOLS

        mcp_tools = [t for t in DEFAULT_ALLOWED_TOOLS if "seosoyoung-attach" in t]
        assert len(mcp_tools) == 5

    def test_viewer_has_no_mcp_tools(self):
        """viewer 역할에는 MCP 도구 없음"""
        from seosoyoung.config import Config

        viewer_tools = Config.ROLE_TOOLS["viewer"]
        mcp_tools = [t for t in viewer_tools if t.startswith("mcp__")]
        assert len(mcp_tools) == 0

    def test_mcp_config_env_vars_complete(self):
        """mcp_config.json에 필요한 환경변수 참조 포함"""
        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        env = config["seosoyoung-attach"]["env"]
        assert "SLACK_BOT_TOKEN" in env
        assert "SLACK_CHANNEL" in env
        assert "SLACK_THREAD_TS" in env
        assert "PYTHONPATH" in env
