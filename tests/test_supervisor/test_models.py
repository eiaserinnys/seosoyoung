"""models.py 단위 테스트"""

from supervisor.models import (
    ExitAction,
    EXIT_CODE_ACTIONS,
    DEFAULT_EXIT_ACTION,
    ProcessConfig,
    ProcessState,
    ProcessStatus,
    RestartPolicy,
    RESTART_DELAY_SECONDS,
)


class TestProcessStatus:
    def test_values(self):
        assert ProcessStatus.STOPPED.value == "stopped"
        assert ProcessStatus.RUNNING.value == "running"
        assert ProcessStatus.RESTARTING.value == "restarting"
        assert ProcessStatus.DEAD.value == "dead"


class TestExitAction:
    def test_values(self):
        assert ExitAction.SHUTDOWN.value == "shutdown"
        assert ExitAction.UPDATE.value == "update"
        assert ExitAction.RESTART.value == "restart"
        assert ExitAction.RESTART_DELAY.value == "restart_delay"

    def test_exit_code_mapping(self):
        assert EXIT_CODE_ACTIONS[0] == ExitAction.SHUTDOWN
        assert EXIT_CODE_ACTIONS[42] == ExitAction.UPDATE
        assert EXIT_CODE_ACTIONS[43] == ExitAction.RESTART

    def test_default_action(self):
        assert DEFAULT_EXIT_ACTION == ExitAction.RESTART_DELAY


class TestRestartPolicy:
    def test_defaults(self):
        policy = RestartPolicy()
        assert policy.use_exit_codes is False
        assert policy.auto_restart is True
        assert policy.restart_delay == RESTART_DELAY_SECONDS
        assert policy.max_restarts == 0

    def test_custom(self):
        policy = RestartPolicy(
            use_exit_codes=True,
            auto_restart=False,
            restart_delay=10.0,
            max_restarts=3,
        )
        assert policy.use_exit_codes is True
        assert policy.auto_restart is False
        assert policy.restart_delay == 10.0
        assert policy.max_restarts == 3


class TestProcessConfig:
    def test_minimal(self):
        cfg = ProcessConfig(name="test", command="python")
        assert cfg.name == "test"
        assert cfg.command == "python"
        assert cfg.args == []
        assert cfg.cwd is None
        assert cfg.log_dir is None
        assert cfg.stdout_log is None
        assert cfg.stderr_log is None

    def test_log_paths(self, tmp_path):
        cfg = ProcessConfig(
            name="bot",
            command="python",
            log_dir=str(tmp_path),
        )
        assert cfg.stdout_log == tmp_path / "bot-out.log"
        assert cfg.stderr_log == tmp_path / "bot-error.log"


class TestProcessState:
    def test_defaults(self):
        cfg = ProcessConfig(name="test", command="python")
        state = ProcessState(config=cfg)
        assert state.status == ProcessStatus.STOPPED
        assert state.pid is None
        assert state.restart_count == 0
        assert state.last_exit_code is None
