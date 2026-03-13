"""supervisor 대시보드 cogito 리플렉션 테스트.

기존 test_dashboard.py와 동일한 fixture를 사용하되,
cogito /reflect 엔드포인트만 검증한다.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

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
    mgr = ProcessManager()
    cfg = ProcessConfig(
        name="bot",
        command=sys.executable,
        args=["-c", "pass"],
        restart_policy=RestartPolicy(use_exit_codes=True),
        log_dir=None,
    )
    mgr.register(cfg)
    mgr._states["bot"].status = ProcessStatus.RUNNING
    mgr._states["bot"].pid = 1234
    return mgr


@pytest.fixture
def client(pm, tmp_path):
    app = create_app(
        process_manager=pm,
        deployer=MagicMock(
            state=MagicMock(value="idle"),
            status=MagicMock(return_value={"state": "idle"}),
        ),
        git_poller=MagicMock(local_head="abc123", remote_head="abc123"),
        session_monitor=MagicMock(active_session_count=MagicMock(return_value=0)),
        log_dir=tmp_path,
        restart_state=_RestartState(),
    )
    return TestClient(app)


class TestSupervisorReflectEndpoints:
    """supervisor 대시보드의 /reflect 엔드포인트 검증."""

    def test_level0(self, client):
        resp = client.get("/reflect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["identity"]["name"] == "supervisor"
        assert data["identity"]["port"] == 8042
        assert len(data["capabilities"]) == 3

    def test_capability_names(self, client):
        resp = client.get("/reflect")
        data = resp.json()
        cap_names = {c["name"] for c in data["capabilities"]}
        assert cap_names == {"process_management", "deployment", "slack_bot"}

    def test_config_all(self, client):
        resp = client.get("/reflect/config")
        assert resp.status_code == 200
        data = resp.json()
        # deployment: GIT_POLL_INTERVAL
        # slack_bot: SLACK_BOT_TOKEN, SLACK_APP_TOKEN
        assert len(data["configs"]) == 3

    def test_config_slack_bot(self, client):
        resp = client.get("/reflect/config/slack_bot")
        assert resp.status_code == 200
        data = resp.json()
        keys = {c["key"] for c in data["configs"]}
        assert keys == {"SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"}
        # sensitive 확인
        for cfg in data["configs"]:
            assert cfg["sensitive"] is True

    def test_config_deployment(self, client):
        resp = client.get("/reflect/config/deployment")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["configs"]) == 1
        assert data["configs"][0]["key"] == "GIT_POLL_INTERVAL"
        assert data["configs"][0]["required"] is False

    def test_source(self, client):
        """declare_capability (함수 없음)이므로 source는 빈 리스트."""
        resp = client.get("/reflect/source")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sources"] == []

    def test_runtime(self, client):
        resp = client.get("/reflect/runtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "pid" in data

    def test_full(self, client):
        resp = client.get("/reflect/full")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "capabilities" in data
        assert "configs" in data
        assert "sources" in data
        assert "runtime" in data


class TestExistingEndpointsUnaffected:
    """cogito 추가 후 기존 API 엔드포인트가 정상 동작하는지 회귀 테스트."""

    def test_status_endpoint(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        assert "processes" in resp.json()

    def test_root_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
