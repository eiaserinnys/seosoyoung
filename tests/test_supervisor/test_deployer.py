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


class TestSupervisorChangeDetection:
    """supervisor 자체 코드 변경 감지 테스트"""

    def test_has_supervisor_changes_true(self, deployer):
        """src/supervisor/ 경로 변경이 있으면 True"""
        files = [
            "src/supervisor/deployer.py",
            "src/seosoyoung/bot.py",
        ]
        assert deployer._has_supervisor_changes(files) is True

    def test_has_supervisor_changes_false(self, deployer):
        """supervisor 외 변경만 있으면 False"""
        files = [
            "src/seosoyoung/bot.py",
            "scripts/start.ps1",
        ]
        assert deployer._has_supervisor_changes(files) is False

    def test_has_supervisor_changes_empty(self, deployer):
        """변경 파일 없으면 False"""
        assert deployer._has_supervisor_changes([]) is False

    def test_get_changed_files_success(self, deployer):
        """git diff 성공 시 파일 목록 반환"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/supervisor/deployer.py\nsrc/seosoyoung/bot.py\n",
            )
            files = deployer._get_changed_files()
            assert files == ["src/supervisor/deployer.py", "src/seosoyoung/bot.py"]

    def test_get_changed_files_failure(self, deployer):
        """git diff 실패 시 빈 리스트"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            files = deployer._get_changed_files()
            assert files == []

    def test_deploy_with_supervisor_changes_raises(self, deployer, mock_pm):
        """supervisor 변경 시 SupervisorRestartRequired 예외 발생"""
        from supervisor.deployer import SupervisorRestartRequired

        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files",
            return_value=["src/supervisor/deployer.py"],
        ), patch.object(deployer, "_do_update"):
            with pytest.raises(SupervisorRestartRequired):
                deployer.tick()

        # supervisor 변경 시 프로세스 중지는 호출됨
        mock_pm.stop_all.assert_called_once()

    def test_deploy_without_supervisor_changes_normal(self, deployer, mock_pm):
        """supervisor 외 변경 시 정상 배포"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files",
            return_value=["src/seosoyoung/bot.py"],
        ), patch.object(deployer, "_do_update"):
            deployer.tick()

        assert deployer.state == DeployState.IDLE
        mock_pm.stop_all.assert_called_once()
        assert mock_pm.start.call_count == 2


class TestDeployWebhookNotifications:
    """배포 시 Slack 웹훅 알림 테스트"""

    def test_success_sends_start_and_success(self, deployer, mock_pm):
        """성공 배포 시 시작/완료 알림 전송"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files", return_value=["src/seosoyoung/bot.py"]
        ), patch.object(deployer, "_do_update"), \
             patch("supervisor.deployer.notify_deploy_start") as mock_start, \
             patch("supervisor.deployer.notify_deploy_success") as mock_success, \
             patch("supervisor.deployer.notify_deploy_failure") as mock_failure:
            deployer.tick()

        mock_start.assert_called_once_with(deployer._paths, deployer._webhook_config)
        mock_success.assert_called_once_with(deployer._webhook_config)
        mock_failure.assert_not_called()

    def test_failure_sends_start_and_failure(self, deployer, mock_pm):
        """실패 배포 시 시작/실패 알림 전송"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files", return_value=["src/seosoyoung/bot.py"]
        ), patch.object(
            deployer, "_do_update", side_effect=Exception("pull failed")
        ), patch("supervisor.deployer.notify_deploy_start") as mock_start, \
             patch("supervisor.deployer.notify_deploy_success") as mock_success, \
             patch("supervisor.deployer.notify_deploy_failure") as mock_failure:
            deployer.tick()

        mock_start.assert_called_once()
        mock_success.assert_not_called()
        mock_failure.assert_called_once()
        # 에러 메시지가 키워드 인수로 전달되어야 함
        assert mock_failure.call_args[1]["error"] == "pull failed"

    def test_supervisor_change_no_webhook(self, deployer, mock_pm):
        """supervisor 코드 변경 시에는 웹훅 보내지 않음 (watchdog이 처리)"""
        from supervisor.deployer import SupervisorRestartRequired

        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files",
            return_value=["src/supervisor/deployer.py"],
        ), patch("supervisor.deployer.notify_deploy_start") as mock_start, \
             patch("supervisor.deployer.notify_deploy_success") as mock_success:
            with pytest.raises(SupervisorRestartRequired):
                deployer.tick()

        mock_start.assert_not_called()
        mock_success.assert_not_called()

    def test_webhook_failure_does_not_block_deploy(self, deployer, mock_pm):
        """웹훅 전송 실패가 배포를 중단하지 않음"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files", return_value=["src/seosoyoung/bot.py"]
        ), patch.object(deployer, "_do_update"), \
             patch(
                 "supervisor.deployer.notify_deploy_start",
                 side_effect=Exception("webhook error"),
             ), \
             patch("supervisor.deployer.notify_deploy_success"):
            deployer.tick()

        # 배포는 성공해야 함
        assert deployer.state == DeployState.IDLE
        mock_pm.stop_all.assert_called_once()
        assert mock_pm.start.call_count == 2


class TestStatus:
    def test_status_returns_current_state(self, deployer):
        info = deployer.status()
        assert info["state"] == "idle"

    def test_status_after_change(self, deployer):
        deployer.notify_change()
        info = deployer.status()
        assert info["state"] == "pending"


class TestChangeDetectedNotification:
    """변경 감지 알림 테스트"""

    def test_notify_change_sends_change_detected(self, deployer):
        """idle → pending 전환 시 change_detected 알림 전송"""
        with patch("supervisor.deployer.notify_change_detected") as mock_notify:
            deployer.notify_change()

        mock_notify.assert_called_once_with(deployer._paths, deployer._webhook_config)

    def test_notify_change_already_pending_no_second_notification(self, deployer):
        """이미 pending 상태이면 알림을 다시 보내지 않음"""
        with patch("supervisor.deployer.notify_change_detected") as mock_notify:
            deployer.notify_change()
            deployer.notify_change()  # 두 번째 호출

        mock_notify.assert_called_once()  # 한 번만 호출

    def test_notify_change_webhook_failure_does_not_block(self, deployer):
        """알림 전송 실패가 상태 전환을 막지 않음"""
        with patch(
            "supervisor.deployer.notify_change_detected",
            side_effect=Exception("webhook error"),
        ):
            deployer.notify_change()  # 예외가 전파되지 않아야 함

        assert deployer.state == DeployState.PENDING


class TestWaitingSessionsNotification:
    """세션 대기 알림 테스트"""

    def test_pending_to_waiting_sends_waiting_notification(self, deployer, mock_session_monitor):
        """pending → waiting_sessions 전환 시 waiting_sessions 알림 전송"""
        deployer.notify_change()
        mock_session_monitor.is_safe_to_deploy.return_value = False

        with patch("supervisor.deployer.notify_waiting_sessions") as mock_notify:
            deployer.tick()

        mock_notify.assert_called_once_with(deployer._webhook_config)

    def test_waiting_sessions_stays_no_repeat_notification(self, deployer, mock_session_monitor):
        """waiting_sessions 상태 유지 시 추가 알림을 보내지 않음"""
        from supervisor.deployer import DeployState
        deployer._state = DeployState.WAITING_SESSIONS
        mock_session_monitor.is_safe_to_deploy.return_value = False

        with patch("supervisor.deployer.notify_waiting_sessions") as mock_notify:
            deployer.tick()

        mock_notify.assert_not_called()

    def test_waiting_sessions_webhook_failure_does_not_block(self, deployer, mock_session_monitor):
        """세션 대기 알림 실패가 상태 전환을 막지 않음"""
        deployer.notify_change()
        mock_session_monitor.is_safe_to_deploy.return_value = False

        with patch(
            "supervisor.deployer.notify_waiting_sessions",
            side_effect=Exception("webhook error"),
        ):
            deployer.tick()  # 예외가 전파되지 않아야 함

        assert deployer.state == DeployState.WAITING_SESSIONS
