"""대시보드 API 테스트"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from supervisor.models import (
    ProcessConfig,
    ProcessState,
    ProcessStatus,
    RestartPolicy,
)
from supervisor.process_manager import ProcessManager
from supervisor.dashboard import create_app


@pytest.fixture
def pm():
    """실제 ProcessManager (mock 없이)"""
    mgr = ProcessManager()
    cfg_bot = ProcessConfig(
        name="bot",
        command=sys.executable,
        args=["-c", "pass"],
        restart_policy=RestartPolicy(use_exit_codes=True),
        log_dir=None,
    )
    cfg_mcp = ProcessConfig(
        name="mcp",
        command=sys.executable,
        args=["-c", "pass"],
        log_dir=None,
    )
    mgr.register(cfg_bot)
    mgr.register(cfg_mcp)
    # 상태만 조작 (실제 프로세스는 띄우지 않음)
    mgr._states["bot"].status = ProcessStatus.RUNNING
    mgr._states["bot"].pid = 1234
    mgr._states["mcp"].status = ProcessStatus.STOPPED
    return mgr


@pytest.fixture
def mock_deployer():
    deployer = MagicMock()
    deployer.state.value = "idle"
    deployer.status.return_value = {"state": "idle"}
    return deployer


@pytest.fixture
def mock_git_poller():
    poller = MagicMock()
    poller.local_head = "abc1234567890"
    poller.remote_head = "abc1234567890"
    return poller


@pytest.fixture
def client(pm, mock_deployer, mock_git_poller, tmp_path):
    app = create_app(
        process_manager=pm,
        deployer=mock_deployer,
        git_poller=mock_git_poller,
        log_dir=tmp_path,
    )
    return TestClient(app)


class TestGetStatus:
    def test_returns_process_status(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "processes" in data
        assert "bot" in data["processes"]
        assert "mcp" in data["processes"]

    def test_process_fields(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        bot = data["processes"]["bot"]
        assert bot["status"] == "running"
        assert bot["pid"] == 1234

    def test_deploy_state(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "deploy" in data
        assert data["deploy"]["state"] == "idle"

    def test_git_state(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "git" in data
        assert "local_head" in data["git"]


class TestProcessControl:
    def test_stop_process(self, client, pm):
        with patch.object(pm, "stop") as mock_stop:
            resp = client.post("/api/process/bot/stop")
            assert resp.status_code == 200
            mock_stop.assert_called_once_with("bot")

    def test_start_process(self, client, pm):
        with patch.object(pm, "start") as mock_start:
            resp = client.post("/api/process/bot/start")
            assert resp.status_code == 200
            mock_start.assert_called_once_with("bot")

    def test_restart_process(self, client, pm):
        with patch.object(pm, "restart") as mock_restart:
            resp = client.post("/api/process/bot/restart")
            assert resp.status_code == 200
            mock_restart.assert_called_once_with("bot")

    def test_unknown_process(self, client, pm):
        with patch.object(pm, "stop", side_effect=KeyError("등록되지 않은 프로세스: unknown")):
            resp = client.post("/api/process/unknown/stop")
            assert resp.status_code == 404

    def test_invalid_action(self, client):
        resp = client.post("/api/process/bot/kill")
        assert resp.status_code == 400


class TestDeploy:
    def test_deploy_trigger(self, client, mock_deployer):
        resp = client.post("/api/deploy")
        assert resp.status_code == 200
        mock_deployer.notify_change.assert_called_once()

    def test_deploy_returns_state(self, client):
        resp = client.post("/api/deploy")
        data = resp.json()
        assert "state" in data


class TestLogs:
    def test_get_logs(self, client, tmp_path):
        # 로그 파일 생성
        log_file = tmp_path / "bot-out.log"
        lines = [f"line {i}\n" for i in range(150)]
        log_file.write_text("".join(lines), encoding="utf-8")

        resp = client.get("/api/logs/bot")
        assert resp.status_code == 200
        data = resp.json()
        assert "lines" in data
        # 기본 100줄
        assert len(data["lines"]) == 100

    def test_get_logs_custom_count(self, client, tmp_path):
        log_file = tmp_path / "bot-out.log"
        lines = [f"line {i}\n" for i in range(50)]
        log_file.write_text("".join(lines), encoding="utf-8")

        resp = client.get("/api/logs/bot?n=20")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 20

    def test_get_logs_no_file(self, client):
        resp = client.get("/api/logs/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == []

    def test_path_traversal_rejected(self, client):
        # URL-encoded slashes become routing mismatches (404) or validated (400)
        resp = client.get("/api/logs/..%2Fetc")
        assert resp.status_code in (400, 404)

    def test_dotdot_name_rejected(self, client):
        resp = client.get("/api/logs/..etc")
        assert resp.status_code == 400

    def test_get_error_logs(self, client, tmp_path):
        log_file = tmp_path / "bot-error.log"
        log_file.write_text("error line 1\nerror line 2\n", encoding="utf-8")

        resp = client.get("/api/logs/bot?type=error")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 2


class TestStaticUI:
    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
