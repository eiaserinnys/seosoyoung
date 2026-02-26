"""config.py 단위 테스트"""

import os
from unittest.mock import patch

import pytest

from supervisor.config import (
    build_process_configs,
    _resolve_paths,
    _find_node,
    _find_supergateway,
    _mcp_outline_available,
)


class TestResolvePaths:
    def test_default_paths(self):
        paths = _resolve_paths()
        assert "root" in paths
        assert "runtime" in paths
        assert "workspace" in paths
        assert "venv_python" in paths
        assert "mcp_venv_python" in paths
        assert "logs" in paths

    def test_custom_root(self, tmp_path):
        with patch.dict(os.environ, {"SOYOUNG_ROOT": str(tmp_path)}):
            paths = _resolve_paths()
            assert paths["root"] == tmp_path
            assert "seosoyoung_runtime" in str(paths["runtime"])
            assert "slackbot_workspace" in str(paths["workspace"])

    def test_mcp_venv_python_path(self):
        paths = _resolve_paths()
        assert "mcp_venv" in str(paths["mcp_venv_python"])
        assert str(paths["mcp_venv_python"]).endswith("python.exe")


class TestFinders:
    def test_find_node_from_path(self):
        with patch("shutil.which", return_value="C:/node/node.exe"):
            assert _find_node() == "C:/node/node.exe"

    def test_find_node_not_found(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                _find_node()

    def test_find_supergateway_from_env(self, tmp_path):
        sg = tmp_path / "index.js"
        sg.write_text("")
        with patch.dict(os.environ, {"SUPERGATEWAY_PATH": str(sg)}):
            assert _find_supergateway() == str(sg)

    def test_find_supergateway_not_found(self, tmp_path):
        with patch.dict(os.environ, {
            "SUPERGATEWAY_PATH": "",
            "NPM_GLOBAL_PREFIX": str(tmp_path),
        }):
            with pytest.raises(FileNotFoundError):
                _find_supergateway()

    def test_mcp_outline_available_true(self):
        import sys
        assert _mcp_outline_available(sys.executable) is True

    def test_mcp_outline_available_false(self):
        assert _mcp_outline_available("/nonexistent/python") is False


def _mock_finders():
    """build_process_configs의 finder 함수들을 mock하는 패치 컨텍스트"""
    return [
        patch("supervisor.config._find_node", return_value="node"),
        patch("supervisor.config._find_supergateway", return_value="/path/to/supergateway/index.js"),
        patch("supervisor.config._mcp_outline_available", return_value=True),
    ]


class TestBuildProcessConfigs:
    def _build(self):
        patches = _mock_finders()
        for p in patches:
            p.start()
        try:
            return build_process_configs()
        finally:
            for p in patches:
                p.stop()

    def test_returns_at_least_six_configs(self):
        configs = self._build()
        assert len(configs) >= 6

    def test_all_process_names(self):
        configs = self._build()
        names = {c.name for c in configs}
        required = {
            "bot", "mcp-seosoyoung", "seosoyoung-soul",
            "mcp-outline", "mcp-slack", "mcp-trello",
        }
        assert required.issubset(names)
        # rescue-bot, mcp-eb-lore, soul-dashboard는 환경/패키지 유무에 따라 선택적
        assert names - required <= {"rescue-bot", "mcp-eb-lore", "soul-dashboard"}

    def test_bot_config(self):
        configs = self._build()
        bot = next(c for c in configs if c.name == "bot")
        assert "-m" in bot.args
        assert "seosoyoung.slackbot" in bot.args
        assert bot.restart_policy.use_exit_codes is True
        assert bot.log_dir is not None

    def test_mcp_seosoyoung_config(self):
        configs = self._build()
        mcp = next(c for c in configs if c.name == "mcp-seosoyoung")
        assert "-m" in mcp.args
        assert "seosoyoung.mcp" in mcp.args
        assert "--transport=sse" in mcp.args
        assert "--port=3104" in mcp.args
        assert "mcp_venv" in mcp.command
        assert mcp.restart_policy.use_exit_codes is False
        assert mcp.restart_policy.auto_restart is True
        assert mcp.log_dir is not None

    def test_mcp_outline_config(self):
        configs = self._build()
        outline = next(c for c in configs if c.name == "mcp-outline")
        assert "-m" in outline.args
        assert "mcp_outline" in outline.args
        assert "mcp_venv" in outline.command
        assert outline.restart_policy.auto_restart is True
        assert outline.log_dir is not None

    def test_mcp_slack_config(self):
        configs = self._build()
        slack = next(c for c in configs if c.name == "mcp-slack")
        assert "3101" in slack.args
        assert slack.restart_policy.auto_restart is True
        assert slack.log_dir is not None

    def test_mcp_trello_config(self):
        configs = self._build()
        trello = next(c for c in configs if c.name == "mcp-trello")
        assert "3102" in trello.args
        assert trello.restart_policy.auto_restart is True
        assert trello.log_dir is not None

    def test_seosoyoung_soul_config(self):
        configs = self._build()
        soul = next(c for c in configs if c.name == "seosoyoung-soul")
        assert "-m" in soul.args
        assert "uvicorn" in soul.args
        assert "seosoyoung.soul.main:app" in soul.args
        assert "--port" in soul.args
        assert "3105" in soul.args
        assert "--host" in soul.args
        assert "127.0.0.1" in soul.args
        assert soul.port == 3105
        assert soul.restart_policy.use_exit_codes is False
        assert soul.restart_policy.auto_restart is True
        assert soul.log_dir is not None

    def test_all_configs_have_log_dir(self):
        configs = self._build()
        for cfg in configs:
            assert cfg.log_dir is not None, f"{cfg.name}에 log_dir가 없습니다"


class TestSoulDashboardConfig:
    """soul-dashboard 프로세스 설정 테스트."""

    def _build_with_dashboard(self, tmp_path):
        """tsx와 서버 엔트리 파일이 존재하는 환경을 시뮬레이트."""
        # 가짜 dashboard 디렉토리 구조 생성
        workspace = tmp_path / "slackbot_workspace"
        dashboard_dir = (
            workspace / ".projects" / "seosoyoung"
            / "src" / "soul-dashboard"
        )
        tsx_dir = dashboard_dir / "node_modules" / "tsx" / "dist"
        tsx_dir.mkdir(parents=True)
        (tsx_dir / "cli.mjs").write_text("// tsx cli")

        server_dir = dashboard_dir / "server"
        server_dir.mkdir(parents=True)
        (server_dir / "index.ts").write_text("// server")

        # runtime 디렉토리
        runtime = tmp_path / "seosoyoung_runtime"
        (runtime / "venv" / "Scripts").mkdir(parents=True)
        (runtime / "venv" / "Scripts" / "python.exe").write_text("")
        (runtime / "mcp_venv" / "Scripts").mkdir(parents=True)
        (runtime / "mcp_venv" / "Scripts" / "python.exe").write_text("")
        (runtime / "logs").mkdir(parents=True)

        patches = [
            patch.dict(os.environ, {"SOYOUNG_ROOT": str(tmp_path)}),
            patch("supervisor.config._find_node", return_value="node"),
            patch("supervisor.config._find_supergateway", return_value="/sg/index.js"),
            patch("supervisor.config._mcp_outline_available", return_value=False),
        ]
        for p in patches:
            p.start()
        try:
            return build_process_configs()
        finally:
            for p in patches:
                p.stop()

    def test_dashboard_included_when_files_exist(self, tmp_path):
        """tsx와 서버 파일이 있으면 soul-dashboard 프로세스가 포함됨."""
        configs = self._build_with_dashboard(tmp_path)
        names = {c.name for c in configs}
        assert "soul-dashboard" in names

    def test_dashboard_config_details(self, tmp_path):
        """soul-dashboard 프로세스 설정이 올바른지 확인."""
        configs = self._build_with_dashboard(tmp_path)
        dashboard = next(c for c in configs if c.name == "soul-dashboard")

        assert dashboard.command == "node"
        assert any("tsx" in arg and "cli.mjs" in arg for arg in dashboard.args)
        assert any("index.ts" in arg for arg in dashboard.args)
        assert dashboard.port == 3109
        assert dashboard.restart_policy.auto_restart is True
        assert dashboard.restart_policy.use_exit_codes is False
        assert dashboard.log_dir is not None

    def test_dashboard_excluded_when_tsx_missing(self, tmp_path):
        """tsx가 설치되지 않으면 soul-dashboard가 제외됨."""
        # tsx 없이 서버 파일만 존재
        workspace = tmp_path / "slackbot_workspace"
        dashboard_dir = (
            workspace / ".projects" / "seosoyoung"
            / "src" / "soul-dashboard"
        )
        server_dir = dashboard_dir / "server"
        server_dir.mkdir(parents=True)
        (server_dir / "index.ts").write_text("// server")

        runtime = tmp_path / "seosoyoung_runtime"
        (runtime / "venv" / "Scripts").mkdir(parents=True)
        (runtime / "venv" / "Scripts" / "python.exe").write_text("")
        (runtime / "mcp_venv" / "Scripts").mkdir(parents=True)
        (runtime / "mcp_venv" / "Scripts" / "python.exe").write_text("")
        (runtime / "logs").mkdir(parents=True)

        patches = [
            patch.dict(os.environ, {"SOYOUNG_ROOT": str(tmp_path)}),
            patch("supervisor.config._find_node", return_value="node"),
            patch("supervisor.config._find_supergateway", return_value="/sg/index.js"),
            patch("supervisor.config._mcp_outline_available", return_value=False),
        ]
        for p in patches:
            p.start()
        try:
            configs = build_process_configs()
        finally:
            for p in patches:
                p.stop()

        names = {c.name for c in configs}
        assert "soul-dashboard" not in names
