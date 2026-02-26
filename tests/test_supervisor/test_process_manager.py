"""ProcessManager 단위 테스트"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from supervisor.models import (
    ExitAction,
    ProcessConfig,
    ProcessState,
    ProcessStatus,
    RestartPolicy,
)
from supervisor.process_manager import ProcessManager


@pytest.fixture
def pm():
    return ProcessManager()


@pytest.fixture
def bot_config(tmp_path):
    return ProcessConfig(
        name="bot",
        command=sys.executable,
        args=["-c", "import sys; sys.exit(0)"],
        cwd=str(tmp_path),
        restart_policy=RestartPolicy(use_exit_codes=True),
        log_dir=str(tmp_path / "logs"),
    )


@pytest.fixture
def sleeper_config(tmp_path):
    """오래 실행되는 프로세스 (10초 sleep)"""
    return ProcessConfig(
        name="sleeper",
        command=sys.executable,
        args=["-c", "import time; time.sleep(10)"],
        cwd=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
    )


class TestRegister:
    def test_register(self, pm, bot_config):
        pm.register(bot_config)
        assert "bot" in pm.registered_names

    def test_register_duplicate(self, pm, bot_config):
        pm.register(bot_config)
        with pytest.raises(ValueError, match="이미 등록된"):
            pm.register(bot_config)


class TestStartStop:
    def test_start_creates_process(self, pm, sleeper_config):
        pm.register(sleeper_config)
        pm.start("sleeper")

        assert pm.is_running("sleeper")
        state = pm._states["sleeper"]
        assert state.status == ProcessStatus.RUNNING
        assert state.pid is not None

        pm.stop("sleeper")

    def test_start_creates_log_files(self, pm, sleeper_config, tmp_path):
        pm.register(sleeper_config)
        pm.start("sleeper")

        log_dir = tmp_path / "logs"
        assert log_dir.exists()
        assert (log_dir / "sleeper-out.log").exists()
        assert (log_dir / "sleeper-error.log").exists()

        pm.stop("sleeper")

    def test_start_unregistered(self, pm):
        with pytest.raises(KeyError, match="등록되지 않은"):
            pm.start("unknown")

    def test_start_already_running(self, pm, sleeper_config):
        pm.register(sleeper_config)
        pm.start("sleeper")
        # 두 번째 start는 경고만 출력, 에러 없음
        pm.start("sleeper")
        pm.stop("sleeper")

    def test_stop_returns_exit_code(self, pm, bot_config):
        pm.register(bot_config)
        pm.start("bot")
        # 짧은 프로세스이므로 잠시 대기
        time.sleep(0.5)
        exit_code = pm.stop("bot")
        # 이미 종료되었거나 정상 종료 (0)
        assert exit_code is not None or pm._states["bot"].last_exit_code == 0

    def test_stop_already_stopped(self, pm, bot_config):
        pm.register(bot_config)
        result = pm.stop("bot")
        assert result is None

    def test_stop_terminates_process(self, pm, sleeper_config):
        pm.register(sleeper_config)
        pm.start("sleeper")
        assert pm.is_running("sleeper")

        exit_code = pm.stop("sleeper")
        assert not pm.is_running("sleeper")
        state = pm._states["sleeper"]
        assert state.status == ProcessStatus.STOPPED
        assert state.pid is None


class TestRestart:
    def test_restart(self, pm, sleeper_config):
        pm.register(sleeper_config)
        pm.start("sleeper")
        old_pid = pm._states["sleeper"].pid

        pm.restart("sleeper")
        new_pid = pm._states["sleeper"].pid

        assert new_pid != old_pid
        assert pm.is_running("sleeper")
        assert pm._states["sleeper"].restart_count == 1

        pm.stop("sleeper")


class TestPoll:
    def test_poll_running(self, pm, sleeper_config):
        pm.register(sleeper_config)
        pm.start("sleeper")

        result = pm.poll("sleeper")
        assert result is None  # 아직 실행 중
        assert pm._states["sleeper"].status == ProcessStatus.RUNNING

        pm.stop("sleeper")

    def test_poll_exited(self, pm, bot_config):
        pm.register(bot_config)
        pm.start("bot")
        time.sleep(0.5)

        exit_code = pm.poll("bot")
        assert exit_code == 0
        assert pm._states["bot"].status == ProcessStatus.STOPPED

    def test_poll_already_stopped_returns_none(self, pm, bot_config):
        """한번 처리된 종료는 이후 poll에서 None 반환 (중복 처리 방지)"""
        pm.register(bot_config)
        pm.start("bot")
        time.sleep(0.5)

        first = pm.poll("bot")
        assert first == 0
        second = pm.poll("bot")
        assert second is None


class TestExitCodeResolution:
    def test_exit_0_shutdown(self, pm):
        assert pm.resolve_exit_action(0) == ExitAction.SHUTDOWN

    def test_exit_42_update(self, pm):
        assert pm.resolve_exit_action(42) == ExitAction.UPDATE

    def test_exit_43_restart(self, pm):
        assert pm.resolve_exit_action(43) == ExitAction.RESTART

    def test_exit_other_restart_delay(self, pm):
        assert pm.resolve_exit_action(1) == ExitAction.RESTART_DELAY
        assert pm.resolve_exit_action(137) == ExitAction.RESTART_DELAY

    def test_exit_none(self, pm):
        assert pm.resolve_exit_action(None) == ExitAction.RESTART_DELAY


class TestStatus:
    def test_status_all(self, pm, sleeper_config, bot_config):
        pm.register(sleeper_config)
        pm.register(bot_config)
        pm.start("sleeper")

        status = pm.status()
        assert "sleeper" in status
        assert "bot" in status
        assert status["sleeper"]["status"] == "running"
        assert status["bot"]["status"] == "stopped"

        pm.stop("sleeper")


class TestStopAll:
    def test_stop_all(self, pm, tmp_path):
        cfg1 = ProcessConfig(
            name="p1",
            command=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
            cwd=str(tmp_path),
        )
        cfg2 = ProcessConfig(
            name="p2",
            command=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
            cwd=str(tmp_path),
        )
        pm.register(cfg1)
        pm.register(cfg2)
        pm.start("p1")
        pm.start("p2")

        assert pm.is_running("p1")
        assert pm.is_running("p2")

        pm.stop_all()

        assert not pm.is_running("p1")
        assert not pm.is_running("p2")


class TestStartFailure:
    def test_start_bad_command(self, pm, tmp_path):
        cfg = ProcessConfig(
            name="bad",
            command="/nonexistent/command",
            cwd=str(tmp_path),
        )
        pm.register(cfg)
        with pytest.raises(FileNotFoundError):
            pm.start("bad")
        assert pm._states["bad"].status == ProcessStatus.DEAD


class TestExitCodeProcess:
    """실제 프로세스를 사용한 exit code 테스트"""

    def test_exit_42(self, pm, tmp_path):
        cfg = ProcessConfig(
            name="exit42",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(42)"],
            cwd=str(tmp_path),
            restart_policy=RestartPolicy(use_exit_codes=True),
        )
        pm.register(cfg)
        pm.start("exit42")
        time.sleep(0.5)
        exit_code = pm.poll("exit42")
        assert exit_code == 42
        assert pm.resolve_exit_action(exit_code) == ExitAction.UPDATE

    def test_exit_43(self, pm, tmp_path):
        cfg = ProcessConfig(
            name="exit43",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(43)"],
            cwd=str(tmp_path),
            restart_policy=RestartPolicy(use_exit_codes=True),
        )
        pm.register(cfg)
        pm.start("exit43")
        time.sleep(0.5)
        exit_code = pm.poll("exit43")
        assert exit_code == 43
        assert pm.resolve_exit_action(exit_code) == ExitAction.RESTART
