"""허용 도구 목록 단일화 테스트

config.py의 ROLE_TOOLS가 단일 소스인지 확인합니다.
"""

from seosoyoung.config import Config


class TestRoleToolsSingleSource:
    """ROLE_TOOLS 단일 소스 검증"""

    def test_admin_role_exists(self):
        """admin 역할이 존재"""
        assert "admin" in Config.auth.role_tools

    def test_viewer_role_exists(self):
        """viewer 역할이 존재"""
        assert "viewer" in Config.auth.role_tools

    def test_admin_has_base_tools(self):
        """admin에 기본 도구가 포함"""
        admin_tools = Config.auth.role_tools["admin"]
        for tool in ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"]:
            assert tool in admin_tools, f"{tool}이 admin 도구에 없음"

    def test_admin_has_mcp_tools(self):
        """admin에 MCP 도구가 포함"""
        admin_tools = Config.auth.role_tools["admin"]
        assert any("slack_attach_file" in t for t in admin_tools)
        assert any("slack_get_context" in t for t in admin_tools)

    def test_admin_has_npc_tools(self):
        """admin에 NPC 도구가 포함"""
        admin_tools = Config.auth.role_tools["admin"]
        assert any("npc_talk" in t for t in admin_tools)

    def test_viewer_is_readonly(self):
        """viewer는 읽기 전용 도구만 포함"""
        viewer_tools = Config.auth.role_tools["viewer"]
        assert "Read" in viewer_tools
        assert "Write" not in viewer_tools
        assert "Bash" not in viewer_tools

    def test_agent_runner_uses_config(self):
        """agent_runner가 Config.auth.role_tools를 참조하는지 확인"""
        from seosoyoung.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner()
        # 기본 allowed_tools가 Config.auth.role_tools["admin"]과 동일
        assert runner.allowed_tools == Config.auth.role_tools["admin"]

    def test_no_duplicate_default_allowed_tools(self):
        """agent_runner에 별도 DEFAULT_ALLOWED_TOOLS가 없어야 함"""
        import seosoyoung.claude.agent_runner as ar
        assert not hasattr(ar, "DEFAULT_ALLOWED_TOOLS"), \
            "DEFAULT_ALLOWED_TOOLS should be removed; use Config.auth.role_tools instead"
