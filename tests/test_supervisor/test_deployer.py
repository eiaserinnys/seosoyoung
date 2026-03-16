"""Deployer 상태 머신 단위 테스트"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from supervisor.deployer import Deployer, DeployState, DeployUpdateError


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
        "soulstream_runtime": tmp_path / "soulstream_runtime",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    monitored_repos = {"runtime": paths["runtime"]}
    return Deployer(
        process_manager=mock_pm,
        session_monitor=mock_session_monitor,
        paths=paths,
        monitored_repos=monitored_repos,
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

    def test_waiting_sessions_waits_indefinitely(self, deployer, mock_session_monitor):
        """waiting_sessions는 타임아웃 없이 세션 종료까지 무한 대기한다."""
        deployer._state = DeployState.WAITING_SESSIONS
        deployer._waiting_since = 0.0  # 오래 전부터 대기 중인 것처럼 시뮬레이션
        mock_session_monitor.is_safe_to_deploy.return_value = False

        for _ in range(100):
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
    """배포 시 Slack 웹훅 알림 테스트

    deployer._execute_deploy() 정상 완료 시:
      notify_deploy_start → (update) → notify_restart_start → (restart) → notify_restart_complete
    deployer._execute_deploy() 실패 시:
      notify_deploy_start → (update 실패) → notify_deploy_failure
    """

    def test_success_sends_start_and_restart_complete(self, deployer, mock_pm):
        """성공 배포 시 시작/재시작완료 알림 전송"""
        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files", return_value=["src/seosoyoung/bot.py"]
        ), patch.object(deployer, "_do_update"), \
             patch("supervisor.deployer.notify_deploy_start") as mock_start, \
             patch("supervisor.deployer.notify_restart_start") as mock_restart_start, \
             patch("supervisor.deployer.notify_restart_complete") as mock_restart_complete, \
             patch("supervisor.deployer.notify_deploy_failure") as mock_failure:
            deployer.tick()

        mock_start.assert_called_once_with(deployer._paths, deployer._webhook_config)
        mock_restart_start.assert_called_once_with(deployer._webhook_config)
        mock_restart_complete.assert_called_once_with(deployer._webhook_config)
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
             patch("supervisor.deployer.notify_restart_start") as mock_restart_start, \
             patch("supervisor.deployer.notify_restart_complete") as mock_restart_complete, \
             patch("supervisor.deployer.notify_deploy_failure") as mock_failure:
            deployer.tick()

        mock_start.assert_called_once()
        mock_restart_start.assert_not_called()
        mock_restart_complete.assert_not_called()
        mock_failure.assert_called_once()
        # 에러 메시지가 키워드 인수로 전달되어야 함
        assert mock_failure.call_args[1]["error"] == "pull failed"

    def test_supervisor_change_no_deploy_webhook(self, deployer, mock_pm):
        """supervisor 코드 변경 시에는 deploy 웹훅 보내지 않음 (watchdog이 처리)"""
        from supervisor.deployer import SupervisorRestartRequired

        deployer._state = DeployState.PENDING
        deployer._session_monitor.is_safe_to_deploy.return_value = True

        with patch.object(
            deployer, "_get_changed_files",
            return_value=["src/supervisor/deployer.py"],
        ), patch("supervisor.deployer.notify_deploy_start") as mock_start, \
             patch("supervisor.deployer.notify_restart_complete") as mock_complete:
            with pytest.raises(SupervisorRestartRequired):
                deployer.tick()

        mock_start.assert_not_called()
        # restart_start는 notify_and_mark_restart에서 호출됨 (supervisor 재시작 알림)
        mock_complete.assert_not_called()

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
             patch("supervisor.deployer.notify_restart_start"), \
             patch("supervisor.deployer.notify_restart_complete"):
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

    def test_status_idle_has_no_waiting_seconds(self, deployer):
        """idle 상태에서는 waiting_seconds가 포함되지 않음"""
        info = deployer.status()
        assert "waiting_seconds" not in info

    def test_status_waiting_sessions_has_waiting_seconds(self, deployer, mock_session_monitor):
        """waiting_sessions 상태에서는 대기 시간이 포함됨"""
        deployer.notify_change()
        mock_session_monitor.is_safe_to_deploy.return_value = False
        deployer.tick()  # pending → waiting_sessions
        info = deployer.status()
        assert info["state"] == "waiting_sessions"
        assert "waiting_seconds" in info
        assert isinstance(info["waiting_seconds"], int)
        assert info["waiting_seconds"] >= 0


class TestChangeDetectedNotification:
    """변경 감지 알림 테스트"""

    def test_notify_change_sends_change_detected(self, deployer):
        """idle → pending 전환 시 change_detected 알림 전송"""
        with patch("supervisor.deployer.notify_change_detected") as mock_notify:
            deployer.notify_change()

        mock_notify.assert_called_once_with(
            deployer._monitored_repos, deployer._webhook_config,
        )

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

    def test_monitored_repos_passed_to_notification(self, mock_pm, mock_session_monitor, tmp_path):
        """monitored_repos로 등록된 모든 리포가 알림에 전달된다"""
        paths = {
            "runtime": tmp_path / "runtime",
            "workspace": tmp_path / "workspace",
            "logs": tmp_path / "logs",
        }
        for p in paths.values():
            p.mkdir(parents=True, exist_ok=True)
        monitored = {
            "runtime": paths["runtime"],
            "seosoyoung": tmp_path / "seosoyoung",
            "seosoyoung-plugins": tmp_path / "plugins",
            "soulstream": tmp_path / "soulstream",
        }
        d = Deployer(
            process_manager=mock_pm,
            session_monitor=mock_session_monitor,
            paths=paths,
            monitored_repos=monitored,
        )
        with patch("supervisor.deployer.notify_change_detected") as mock_notify:
            d.notify_change()

        called_repos = mock_notify.call_args[0][0]
        assert set(called_repos.keys()) == {
            "runtime", "seosoyoung", "seosoyoung-plugins", "soulstream",
        }


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


class TestGetRepoHead:
    """_get_repo_head 헬퍼 테스트"""

    def test_success(self, deployer, tmp_path):
        """정상적인 HEAD 반환"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="abc1234def5678\n",
            )
            head = deployer._get_repo_head(tmp_path)
            assert head == "abc1234def5678"

    def test_failure_returns_none(self, deployer, tmp_path):
        """git rev-parse 실패 시 None"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error",
            )
            head = deployer._get_repo_head(tmp_path)
            assert head is None

    def test_exception_returns_none(self, deployer, tmp_path):
        """예외 발생 시 None"""
        with patch(
            "supervisor.deployer.subprocess.run",
            side_effect=OSError("no git"),
        ):
            head = deployer._get_repo_head(tmp_path)
            assert head is None


class TestGetChangedFilesBetween:
    """_get_changed_files_between 헬퍼 테스트"""

    def test_success(self, deployer, tmp_path):
        """두 커밋 간 변경 파일 목록 반환"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="src/seosoyoung/slackbot/main.py\nsrc/seosoyoung/slackbot/config.py\n",
            )
            files = deployer._get_changed_files_between(tmp_path, "aaa", "bbb")
            assert files == [
                "src/seosoyoung/slackbot/main.py",
                "src/seosoyoung/slackbot/config.py",
            ]

    def test_failure_returns_empty(self, deployer, tmp_path):
        """git diff 실패 시 빈 리스트"""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error",
            )
            files = deployer._get_changed_files_between(tmp_path, "aaa", "bbb")
            assert files == []


class TestBuildSoulDashboard:
    """_build_soul_dashboard 빌드 로직 테스트"""

    def test_build_success(self, deployer, tmp_path):
        """빌드 성공 시 True 반환 (clean install + build)"""
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"), \
             patch("supervisor.deployer.subprocess.run") as mock_run, \
             patch.object(Deployer, "_clean_node_modules"):
            mock_run.return_value = MagicMock(returncode=0)
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is True
        # pnpm install + pnpm run build 두 번 호출
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0][0][0] == ["/usr/bin/pnpm", "install"]
        assert mock_run.call_args_list[1][0][0] == ["/usr/bin/pnpm", "run", "build"]

    def test_clean_node_modules_called_before_install(self, deployer, tmp_path):
        """빌드 전에 항상 _clean_node_modules가 호출된다"""
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        call_order = []

        def track_clean(path):
            call_order.append("clean")

        def track_run(cmd, **kwargs):
            call_order.append(cmd[1] if len(cmd) > 1 else cmd[0])
            return MagicMock(returncode=0)

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"), \
             patch("supervisor.deployer.subprocess.run", side_effect=track_run), \
             patch.object(Deployer, "_clean_node_modules", side_effect=track_clean):
            deployer._build_soul_dashboard(dashboard_dir)

        assert call_order[0] == "clean"
        assert "install" in call_order[1]

    def test_build_failure_returns_false(self, deployer, tmp_path):
        """pnpm run build 실패 시 False 반환"""
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # pnpm install 성공
                return MagicMock(returncode=0, stderr="")
            # pnpm run build 실패
            return MagicMock(returncode=1, stderr="Build error")

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"), \
             patch("supervisor.deployer.subprocess.run", side_effect=side_effect), \
             patch.object(Deployer, "_clean_node_modules"):
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is False

    def test_install_failure_skips_build(self, deployer, tmp_path):
        """pnpm install 실패 시 build를 건너뛰고 False 반환"""
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"), \
             patch("supervisor.deployer.subprocess.run") as mock_run, \
             patch.object(Deployer, "_clean_node_modules"):
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Install error",
            )
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is False
        # install만 호출, build는 호출되지 않음
        mock_run.assert_called_once()

    def test_no_pnpm_returns_false(self, deployer, tmp_path):
        """pnpm이 없으면 False 반환"""
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        with patch("supervisor.deployer.shutil.which", return_value=None):
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is False

    def test_no_directory_returns_false(self, deployer, tmp_path):
        """디렉토리가 없으면 False 반환"""
        dashboard_dir = tmp_path / "nonexistent"

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"):
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is False

    def test_build_timeout_returns_false(self, deployer, tmp_path):
        """빌드 타임아웃 시 False 반환"""
        import subprocess as sp
        dashboard_dir = tmp_path / "src" / "soul-dashboard"
        dashboard_dir.mkdir(parents=True)

        with patch("supervisor.deployer.shutil.which", return_value="/usr/bin/pnpm"), \
             patch(
                 "supervisor.deployer.subprocess.run",
                 side_effect=sp.TimeoutExpired(cmd="pnpm", timeout=300),
             ), \
             patch.object(Deployer, "_clean_node_modules"):
            result = deployer._build_soul_dashboard(dashboard_dir)

        assert result is False


class TestCleanNodeModules:
    """_clean_node_modules 테스트"""

    def test_deletes_node_modules(self, deployer, tmp_path):
        """node_modules를 삭제한다"""
        dashboard_dir = tmp_path / "soul-dashboard"
        dashboard_dir.mkdir()
        node_modules = dashboard_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "some_package").mkdir()

        deployer._clean_node_modules(dashboard_dir)

        assert not node_modules.exists()

    def test_does_not_delete_package_lock(self, deployer, tmp_path):
        """package-lock.json은 삭제하지 않는다 (pnpm-lock.yaml이 정본)"""
        dashboard_dir = tmp_path / "soul-dashboard"
        dashboard_dir.mkdir()
        package_lock = dashboard_dir / "package-lock.json"
        package_lock.write_text("{}")

        deployer._clean_node_modules(dashboard_dir)

        assert package_lock.exists()

    def test_no_node_modules_does_not_fail(self, deployer, tmp_path):
        """node_modules가 없어도 에러 없이 동작한다"""
        dashboard_dir = tmp_path / "soul-dashboard"
        dashboard_dir.mkdir()

        deployer._clean_node_modules(dashboard_dir)  # 예외 없어야 함


class TestEnsureRepoClean:
    """_ensure_repo_clean 테스트"""

    def test_clean_repo_does_nothing(self, deployer, tmp_path):
        """clean 상태면 reset을 호출하지 않는다."""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            # git status --porcelain → 빈 출력 (clean)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
            )
            deployer._ensure_repo_clean(tmp_path, "test-repo")

        # status 한 번만 호출, reset은 호출 안 됨
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["git", "status", "--porcelain"]

    def test_dirty_repo_resets(self, deployer, tmp_path):
        """dirty 상태면 reset --hard origin/main을 실행한다."""
        calls = []

        def side_effect(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout=" M some_file.py\n")
            if cmd == ["git", "reset", "--hard", "origin/main"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0)

        with patch("supervisor.deployer.subprocess.run", side_effect=side_effect):
            deployer._ensure_repo_clean(tmp_path, "test-repo")

        assert ["git", "status", "--porcelain"] in calls
        assert ["git", "reset", "--hard", "origin/main"] in calls

    def test_unmerged_repo_resets(self, deployer, tmp_path):
        """unmerged 상태면 reset --hard origin/main을 실행한다."""
        calls = []

        def side_effect(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=0, stdout="UU conflicted_file.py\n")
            if cmd == ["git", "reset", "--hard", "origin/main"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0)

        with patch("supervisor.deployer.subprocess.run", side_effect=side_effect):
            deployer._ensure_repo_clean(tmp_path, "test-repo")

        assert ["git", "reset", "--hard", "origin/main"] in calls

    def test_status_failure_attempts_reset(self, deployer, tmp_path):
        """git status가 비정상 종료하면 reset을 시도한다."""
        calls = []

        def side_effect(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(returncode=128, stdout="", stderr="fatal: error")
            return MagicMock(returncode=0)

        with patch("supervisor.deployer.subprocess.run", side_effect=side_effect):
            deployer._ensure_repo_clean(tmp_path, "test-repo")

        assert ["git", "reset", "--hard", "origin/main"] in calls

    def test_status_exception_does_not_raise(self, deployer, tmp_path):
        """subprocess 예외가 발생해도 전파하지 않는다."""
        with patch(
            "supervisor.deployer.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            # 예외 없이 반환해야 한다
            deployer._ensure_repo_clean(tmp_path, "test-repo")


class TestForceResetToOrigin:
    """_force_reset_to_origin 테스트"""

    def test_success(self, deployer, tmp_path):
        """fetch + reset 성공 시 정상 반환."""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            deployer._force_reset_to_origin(tmp_path, "test-repo")

        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0][0][0] == ["git", "fetch", "origin", "main"]
        assert mock_run.call_args_list[1][0][0] == [
            "git", "reset", "--hard", "origin/main",
        ]

    def test_fetch_failure_raises(self, deployer, tmp_path):
        """fetch 실패 시 DeployUpdateError 발생."""
        with patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: Could not read from remote repository.",
            )
            with pytest.raises(DeployUpdateError, match="git fetch 실패"):
                deployer._force_reset_to_origin(tmp_path, "test-repo")

    def test_reset_failure_raises(self, deployer, tmp_path):
        """reset 실패 시 DeployUpdateError 발생."""
        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # fetch 성공
                return MagicMock(returncode=0, stdout="", stderr="")
            # reset 실패
            return MagicMock(returncode=1, stdout="", stderr="error: could not reset")

        with patch("supervisor.deployer.subprocess.run", side_effect=side_effect):
            with pytest.raises(DeployUpdateError, match="git reset.*실패"):
                deployer._force_reset_to_origin(tmp_path, "test-repo")

    def test_fetch_oserror_raises_deploy_error(self, deployer, tmp_path):
        """fetch 중 OSError 발생 시 DeployUpdateError로 변환."""
        with patch(
            "supervisor.deployer.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            with pytest.raises(DeployUpdateError, match="git fetch 예외"):
                deployer._force_reset_to_origin(tmp_path, "test-repo")

    def test_reset_oserror_raises_deploy_error(self, deployer, tmp_path):
        """reset 중 OSError 발생 시 DeployUpdateError로 변환."""
        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            raise OSError("filesystem error")

        with patch("supervisor.deployer.subprocess.run", side_effect=side_effect):
            with pytest.raises(DeployUpdateError, match="git reset 예외"):
                deployer._force_reset_to_origin(tmp_path, "test-repo")


class TestDoUpdateGitRecovery:
    """_do_update()의 git 충돌 복구 로직 테스트"""

    def test_runtime_pull_failure_triggers_force_reset(self, deployer):
        """runtime git pull 실패 시 _force_reset_to_origin을 호출한다."""
        with patch.object(deployer, "_ensure_repo_clean"), \
             patch.object(deployer, "_force_reset_to_origin") as mock_force, \
             patch("supervisor.deployer.subprocess.run") as mock_run:
            # git pull 실패
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error: merge conflict",
            )
            try:
                deployer._do_update()
            except Exception:
                pass

        # runtime에 대한 force_reset이 포함되어야 함
        runtime_calls = [
            c for c in mock_force.call_args_list
            if c[0][1] == "runtime"
        ]
        assert len(runtime_calls) == 1
        assert str(runtime_calls[0][0][0]).endswith("runtime")

    def test_runtime_pull_success_no_force_reset(self, deployer):
        """runtime git pull 성공 시 runtime에 대한 _force_reset_to_origin을 호출하지 않는다."""
        with patch.object(deployer, "_ensure_repo_clean"), \
             patch.object(deployer, "_force_reset_to_origin") as mock_force, \
             patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Already up to date.", stderr="",
            )
            try:
                deployer._do_update()
            except Exception:
                pass

        # runtime에 대한 force_reset은 없어야 함
        runtime_calls = [
            c for c in mock_force.call_args_list
            if c[0][1] == "runtime"
        ]
        assert len(runtime_calls) == 0

    def test_runtime_force_reset_failure_raises(self, deployer):
        """runtime force reset 실패 시 DeployUpdateError가 전파된다."""
        with patch.object(deployer, "_ensure_repo_clean"), \
             patch.object(
                 deployer, "_force_reset_to_origin",
                 side_effect=DeployUpdateError("runtime git fetch 실패"),
             ), \
             patch("supervisor.deployer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="conflict",
            )
            with pytest.raises(DeployUpdateError):
                deployer._do_update()

    def test_no_stash_commands_in_runtime_update(self, deployer):
        """runtime 업데이트에서 git stash 명령이 사용되지 않는다."""
        all_commands = []

        def capture_run(cmd, **kwargs):
            all_commands.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(deployer, "_ensure_repo_clean"), \
             patch("supervisor.deployer.subprocess.run", side_effect=capture_run):
            try:
                deployer._do_update()
            except Exception:
                pass

        stash_cmds = [c for c in all_commands if "stash" in str(c)]
        assert stash_cmds == [], f"stash 명령이 발견됨: {stash_cmds}"

    def test_ensure_repo_clean_called_before_pull(self, deployer):
        """_do_update() 시작 시 _ensure_repo_clean이 호출된다."""
        call_order = []

        def track_ensure_clean(repo_path, label):
            call_order.append(("ensure_clean", label))

        def track_run(cmd, **kwargs):
            if "pull" in cmd:
                call_order.append(("pull", cmd))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(
            deployer, "_ensure_repo_clean", side_effect=track_ensure_clean,
        ), patch("supervisor.deployer.subprocess.run", side_effect=track_run):
            try:
                deployer._do_update()
            except Exception:
                pass

        # ensure_clean이 pull보다 먼저 호출됨
        ensure_idx = next(
            i for i, (name, _) in enumerate(call_order) if name == "ensure_clean"
        )
        pull_idx = next(
            i for i, (name, _) in enumerate(call_order) if name == "pull"
        )
        assert ensure_idx < pull_idx


