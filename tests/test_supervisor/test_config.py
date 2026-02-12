"""config.py 단위 테스트"""

import os
from unittest.mock import patch

from supervisor.config import build_process_configs, _resolve_paths


class TestResolvePaths:
    def test_default_paths(self):
        paths = _resolve_paths()
        assert "root" in paths
        assert "runtime" in paths
        assert "workspace" in paths
        assert "venv_python" in paths
        assert "logs" in paths

    def test_custom_root(self, tmp_path):
        with patch.dict(os.environ, {"SOYOUNG_ROOT": str(tmp_path)}):
            paths = _resolve_paths()
            assert paths["root"] == tmp_path
            assert "seosoyoung_runtime" in str(paths["runtime"])
            assert "slackbot_workspace" in str(paths["workspace"])


class TestBuildProcessConfigs:
    def test_returns_two_configs(self):
        configs = build_process_configs()
        assert len(configs) == 2

    def test_bot_config(self):
        configs = build_process_configs()
        bot = next(c for c in configs if c.name == "bot")
        assert "-m" in bot.args
        assert "seosoyoung.main" in bot.args
        assert bot.restart_policy.use_exit_codes is True
        assert bot.env.get("PYTHONUTF8") == "1"
        assert bot.log_dir is not None

    def test_mcp_config(self):
        configs = build_process_configs()
        mcp = next(c for c in configs if c.name == "mcp")
        assert "-m" in mcp.args
        assert "seosoyoung.mcp" in mcp.args
        assert mcp.restart_policy.use_exit_codes is False
        assert mcp.restart_policy.auto_restart is True
        assert mcp.log_dir is not None
