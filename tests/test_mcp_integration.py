"""MCP 서버 연동 테스트

Phase 2: 봇이 Claude Code를 실행할 때 MCP 서버가 연결되는지 검증
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGetRoleConfigMCP:
    """_get_role_config()이 MCP 설정을 전달하는지 검증"""

    def test_admin_config_has_mcp_config(self):
        """admin 역할 config에 mcp_config_path가 설정됨"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("admin")
        assert config["mcp_config_path"] is not None
        assert config["mcp_config_path"].name == "mcp_config.json"

    def test_viewer_config_no_mcp_config(self):
        """viewer 역할은 MCP 도구를 사용하지 않음"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("viewer")
        assert config["mcp_config_path"] is None


class TestMCPToolsInAllowedTools:
    """allowed_tools에 MCP 도구 패턴이 포함되는지 검증"""

    def test_admin_tools_include_mcp_pattern(self):
        """admin 역할에 MCP 도구가 허용됨"""
        from seosoyoung.config import Config

        admin_tools = Config.ROLE_TOOLS["admin"]
        mcp_tools = [t for t in admin_tools if t.startswith("mcp__seosoyoung-attach")]
        assert len(mcp_tools) > 0, "admin에 mcp__seosoyoung-attach 도구가 없음"

    def test_viewer_tools_exclude_mcp(self):
        """viewer 역할에는 MCP 도구가 없음"""
        from seosoyoung.config import Config

        viewer_tools = Config.ROLE_TOOLS["viewer"]
        mcp_tools = [t for t in viewer_tools if t.startswith("mcp__")]
        assert len(mcp_tools) == 0, "viewer에 MCP 도구가 있으면 안됨"

    def test_default_allowed_tools_include_mcp(self):
        """DEFAULT_ALLOWED_TOOLS에도 MCP 도구가 포함됨"""
        from seosoyoung.claude.agent_runner import DEFAULT_ALLOWED_TOOLS

        mcp_tools = [t for t in DEFAULT_ALLOWED_TOOLS if t.startswith("mcp__seosoyoung-attach")]
        assert len(mcp_tools) > 0, "DEFAULT_ALLOWED_TOOLS에 mcp__seosoyoung-attach 도구가 없음"


class TestBuildOptionsEnvInjection:
    """_build_options()가 SLACK_CHANNEL/SLACK_THREAD_TS를 env에 주입하는지 검증"""

    def test_env_includes_slack_context_when_channel_and_thread_provided(self):
        """channel과 thread_ts가 주어지면 env에 포함됨"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner("1234567890.123456", channel="C12345")
        options, _memory_prompt, _anchor_ts = runner._build_options()

        assert options.env is not None
        assert options.env.get("SLACK_CHANNEL") == "C12345"
        assert options.env.get("SLACK_THREAD_TS") == "1234567890.123456"

    def test_env_is_always_dict(self):
        """env는 항상 dict (SDK가 os.environ과 merge하므로)"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner("1234567890.123456", channel="C12345")
        options, _memory_prompt, _anchor_ts = runner._build_options()

        assert isinstance(options.env, dict)
        # SDK가 {**os.environ, **options.env}로 merge하므로
        # options.env에는 슬랙 컨텍스트만 있어도 됨
        assert "SLACK_CHANNEL" in options.env

    def test_env_no_slack_context_when_no_channel_or_thread(self):
        """channel/thread_ts가 없으면 env에 슬랙 컨텍스트가 없음"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()  # channel/thread_ts 미지정
        options, _memory_prompt, _anchor_ts = runner._build_options()

        assert isinstance(options.env, dict)
        assert "SLACK_CHANNEL" not in options.env


class TestMCPConfigFile:
    """mcp_config.json이 올바른 구조인지 검증"""

    def test_mcp_config_exists(self):
        """mcp_config.json 파일이 존재"""
        config_path = Path(__file__).parent.parent / "mcp_config.json"
        assert config_path.exists(), f"mcp_config.json이 없음: {config_path}"

    def test_mcp_config_has_seosoyoung_server(self):
        """설정에 seosoyoung-attach 서버가 정의됨"""
        import json

        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        assert "seosoyoung-attach" in config
        server = config["seosoyoung-attach"]
        assert server["type"] == "stdio"

    def test_mcp_config_env_references(self):
        """env에 SLACK_CHANNEL, SLACK_THREAD_TS 참조가 있음"""
        import json

        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        env = config["seosoyoung-attach"].get("env", {})
        assert "SLACK_CHANNEL" in env
        assert "SLACK_THREAD_TS" in env
