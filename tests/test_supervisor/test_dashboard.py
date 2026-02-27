"""대시보드 API 테스트"""

import sys
import time
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
from supervisor.dashboard import create_app, _RestartState


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
def mock_session_monitor():
    monitor = MagicMock()
    monitor.active_session_count.return_value = 0
    return monitor


@pytest.fixture
def restart_state():
    return _RestartState()


@pytest.fixture
def client(pm, mock_deployer, mock_git_poller, mock_session_monitor, restart_state, tmp_path):
    app = create_app(
        process_manager=pm,
        deployer=mock_deployer,
        git_poller=mock_git_poller,
        session_monitor=mock_session_monitor,
        log_dir=tmp_path,
        restart_state=restart_state,
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

    def test_supervisor_fields(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "supervisor" in data
        sv = data["supervisor"]
        assert "cooldown_remaining" in sv
        assert "active_sessions_count" in sv
        assert sv["active_sessions_count"] == 0
        assert sv["cooldown_remaining"] == 0.0
        # last_restart_time은 노출하지 않음 (monotonic 값은 클라이언트에 무의미)
        assert "last_restart_time" not in sv


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


class TestSupervisorRestart:
    """POST /api/supervisor/restart 엔드포인트 테스트"""

    def test_restart_ok(self, client, restart_state):
        """세션 없고 쿨다운 없으면 재기동 수락"""
        resp = client.post(
            "/api/supervisor/restart",
            json={"force": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert restart_state.restart_requested.is_set()

    def test_restart_no_body(self, client, restart_state):
        """바디 없이 호출해도 기본값으로 동작"""
        resp = client.post("/api/supervisor/restart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_restart_cooldown(self, client, restart_state):
        """쿨다운 중이면 429 응답"""
        # 먼저 한 번 재기동
        restart_state.try_mark_restart()
        # 이벤트를 클리어하여 중복 테스트 가능하게
        restart_state.restart_requested.clear()

        resp = client.post(
            "/api/supervisor/restart",
            json={"force": False},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert "cooldown_remaining" in data["detail"]
        assert data["detail"]["cooldown_remaining"] > 0

    def test_double_restart_second_blocked(self, client, restart_state):
        """첫 번째 재기동 수락 후 즉시 두 번째 요청은 429"""
        resp1 = client.post("/api/supervisor/restart", json={"force": False})
        assert resp1.status_code == 200
        assert resp1.json()["ok"] is True

        resp2 = client.post("/api/supervisor/restart", json={"force": False})
        assert resp2.status_code == 429

    def test_restart_active_sessions_warning(
        self, client, mock_session_monitor, restart_state,
    ):
        """활성 세션이 있고 force가 아니면 경고 응답"""
        mock_session_monitor.active_session_count.return_value = 2

        resp = client.post(
            "/api/supervisor/restart",
            json={"force": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["warning"] is True
        assert data["active_sessions_count"] == 2
        # 재기동 시그널은 보내지 않음
        assert not restart_state.restart_requested.is_set()

    def test_restart_force_with_sessions(
        self, client, mock_session_monitor, restart_state,
    ):
        """force=true이면 세션이 있어도 재기동"""
        mock_session_monitor.active_session_count.return_value = 3

        resp = client.post(
            "/api/supervisor/restart",
            json={"force": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert restart_state.restart_requested.is_set()


class TestRestartState:
    """_RestartState 내부 클래스 테스트"""

    def test_initial_no_cooldown(self):
        state = _RestartState()
        assert state.cooldown_remaining() == 0.0
        assert not state.is_in_cooldown()

    def test_try_mark_restart_sets_event(self):
        state = _RestartState()
        assert not state.restart_requested.is_set()
        remaining = state.try_mark_restart()
        assert remaining == 0.0
        assert state.restart_requested.is_set()

    def test_cooldown_after_mark(self):
        state = _RestartState()
        state.try_mark_restart()
        assert state.is_in_cooldown()
        assert state.cooldown_remaining() > 0

    def test_try_mark_restart_blocked_during_cooldown(self):
        """쿨다운 중 try_mark_restart는 남은 시간을 반환하고 이벤트를 설정하지 않음"""
        state = _RestartState()
        # 첫 번째: 수락
        assert state.try_mark_restart() == 0.0
        state.restart_requested.clear()
        # 두 번째: 쿨다운으로 거부
        remaining = state.try_mark_restart()
        assert remaining > 0
        assert not state.restart_requested.is_set()

    def test_cooldown_expires(self):
        state = _RestartState()
        # 수동으로 과거 시간 설정하여 쿨다운 만료 시뮬레이션
        state._last_restart_time = time.monotonic() - 120
        assert not state.is_in_cooldown()
        assert state.cooldown_remaining() == 0.0


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
