"""Deployer 상태 머신 단위 테스트"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from supervisor.deployer import Deployer, DeployState


class TestDeployState:
    def test_states_exist(self):
        assert DeployState.IDLE.value == "idle"
        assert DeployState.PENDING.value == "pending"
        assert DeployState.WAITING_SESSIONS.value == "waiting_sessions"
        assert DeployState.DEPLOYING.value == "deploying"


@pytest.fixture
def mock_pm():
    pm = MagicMock()
    pm.stop_all = MagicMock()
    pm.registered_names = ["bot", "mcp"]
    return pm


@pytest.fixture
def mock_session_monitor():
    return MagicMock()


@pytest.fixture
def deployer(mock_pm, mock_session_monitor, tmp_path):
    paths = {
        "runtime": tmp_path / "runtime",
        "workspace": tmp_path / "workspace",
        "logs": tmp_path / "logs",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return Deployer(
        process_manager=mock_pm,
        session_monitor=mock_session_monitor,
        paths=paths,
    )


class TestStateTransitions:
    def test_initial_state_is_idle(self, deployer):
        assert deployer.state == DeployState.IDLE

    def test_notify_change_transitions_to_pending(self, deployer):
        """git 변경 감지 알림 → pending"""
        deployer.notify_change()
        assert deployer.state == DeployState.PENDING

    def test_notify_change_when_already_pending(self, deployer):
        """이미 pending이면 상태 유지"""
        deployer.notify_change()
        deployer.notify_change()
        assert deployer.state == DeployState.PENDING

    def test_tick_pending_sessions_active(self, deployer, mock_session_monitor):
        """pending + 세션 있음 → waiting_sessions"""
        deployer.notify_change()
        mock_session_monitor.is_safe_to_deploy.return_value = False
        deployer.tick()
        assert deployer.state == DeployState.WAITING_SESSIONS

    def test_tick_pending_sessions_clear(self, deployer, mock_session_monitor):
        """pending + 세션 없음 → deploying"""
        deployer.notify_change()
        mock_session_monitor.is_safe_to_deploy.return_value = True
        with patch.object(deployer, "_execute_deploy"):
            deployer.tick()
        assert deployer.state == DeployState.IDLE

    def test_tick_waiting_sessions_still_active(self, deployer, mock_session_monitor):
        """waiting_sessions + 세션 아직 있음 → 대기 유지"""
        deployer._state = DeployState.WAITING_SESSIONS
        mock_session_monitor.is_safe_to_deploy.return_value = False
        deployer.tick()
        assert deployer.state == DeployState.WAITING_SESSIONS

    def test_tick_waiting_sessions_cleared(self, deployer, mock_session_monitor):
        """waiting_sessions + 세션 종료 → deploying → idle"""
        deployer._state = DeployState.WAITING_SESSIONS
        mock_session_monitor.is_safe_to_deploy.return_value = True
        with patch.object(deployer, "_execute_deploy"):
            deployer.tick()
        assert deployer.state == DeployState.IDLE

    def test_tick_idle_does_nothing(self, deployer):
        """idle 상태에서 tick은 아무것도 안 함"""
        deployer.tick()
        assert deployer.state == DeployState.IDLE


class TestExecuteDeploy:
    def test_deploy_calls_stop_update_start(self, deployer, mock_pm):
        """배포 시 stop → update → start 순서"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(deployer, "_do_update") as mock_update:
            deployer.tick()

        mock_pm.stop_all.assert_called_once()
        mock_update.assert_called_once()
        # start가 등록된 모든 프로세스에 호출
        assert mock_pm.start.call_count == 2

    def test_deploy_failure_logs_and_restarts(self, deployer, mock_pm):
        """배포 실패 시 idle로 돌아가고 프로세스 재시작 시도"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(deployer, "_do_update", side_effect=Exception("pull failed")):
            deployer.tick()

        # 실패해도 idle로 복구
        assert deployer.state == DeployState.IDLE
        # 프로세스 재시작은 시도
        assert mock_pm.start.call_count >= 1


class TestStatus:
    def test_status_returns_current_state(self, deployer):
        info = deployer.status()
        assert info["state"] == "idle"

    def test_status_after_change(self, deployer):
        deployer.notify_change()
        info = deployer.status()
        assert info["state"] == "pending"
