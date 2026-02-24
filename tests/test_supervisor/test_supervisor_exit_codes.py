"""supervisor exit code 체계 테스트

exit code 매핑:
  0  → SHUTDOWN (정상 종료)
  42 → UPDATE (git pull 후 재시작)
  43 → RESTART (해당 프로세스만 재시작)
  44 → RESTART_SUPERVISOR (supervisor 전체 재시작)
  기타 → RESTART_DELAY (지연 후 재시작)
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from supervisor.models import (
    ExitAction,
    EXIT_CODE_ACTIONS,
    DEFAULT_EXIT_ACTION,
    ProcessConfig,
    ProcessState,
    ProcessStatus,
    RestartPolicy,
)
from supervisor.process_manager import ProcessManager


class TestExitCodeMapping:
    """exit code → ExitAction 매핑 테스트"""

    def test_exit_0_is_shutdown(self):
        assert EXIT_CODE_ACTIONS[0] == ExitAction.SHUTDOWN

    def test_exit_42_is_update(self):
        assert EXIT_CODE_ACTIONS[42] == ExitAction.UPDATE

    def test_exit_43_is_restart(self):
        """exit 43은 해당 프로세스만 재시작"""
        assert EXIT_CODE_ACTIONS[43] == ExitAction.RESTART

    def test_exit_44_is_restart_supervisor(self):
        """exit 44는 supervisor 전체 재시작"""
        assert EXIT_CODE_ACTIONS[44] == ExitAction.RESTART_SUPERVISOR

    def test_unknown_exit_code_default(self):
        """알 수 없는 exit code는 RESTART_DELAY"""
        assert DEFAULT_EXIT_ACTION == ExitAction.RESTART_DELAY
        assert EXIT_CODE_ACTIONS.get(99, DEFAULT_EXIT_ACTION) == ExitAction.RESTART_DELAY

    def test_exit_action_values(self):
        """ExitAction enum 값 확인"""
        assert ExitAction.SHUTDOWN.value == "shutdown"
        assert ExitAction.UPDATE.value == "update"
        assert ExitAction.RESTART.value == "restart"
        assert ExitAction.RESTART_SUPERVISOR.value == "restart_supervisor"
        assert ExitAction.RESTART_DELAY.value == "restart_delay"


class TestProcessManagerResolveExitAction:
    """ProcessManager.resolve_exit_action 테스트"""

    def setup_method(self):
        self.pm = ProcessManager()

    def test_resolve_exit_0(self):
        assert self.pm.resolve_exit_action(0) == ExitAction.SHUTDOWN

    def test_resolve_exit_42(self):
        assert self.pm.resolve_exit_action(42) == ExitAction.UPDATE

    def test_resolve_exit_43(self):
        assert self.pm.resolve_exit_action(43) == ExitAction.RESTART

    def test_resolve_exit_44(self):
        assert self.pm.resolve_exit_action(44) == ExitAction.RESTART_SUPERVISOR

    def test_resolve_exit_none(self):
        assert self.pm.resolve_exit_action(None) == ExitAction.RESTART_DELAY

    def test_resolve_exit_unknown(self):
        assert self.pm.resolve_exit_action(1) == ExitAction.RESTART_DELAY
        assert self.pm.resolve_exit_action(255) == ExitAction.RESTART_DELAY


class TestRestartPolicy:
    """RestartPolicy와 exit code 상호작용 테스트"""

    def test_use_exit_codes_true_bot(self):
        """봇은 use_exit_codes=True → exit code 기반 분기"""
        policy = RestartPolicy(use_exit_codes=True, auto_restart=True)
        assert policy.use_exit_codes is True

    def test_use_exit_codes_false_mcp(self):
        """MCP 서버는 use_exit_codes=False → auto_restart 기반"""
        policy = RestartPolicy(use_exit_codes=False, auto_restart=True)
        assert policy.use_exit_codes is False

    def test_exit_43_with_use_exit_codes_resolves_to_restart(self):
        """use_exit_codes=True + exit 43 → RESTART (프로세스만 재시작)"""
        pm = ProcessManager()
        action = pm.resolve_exit_action(43)
        assert action == ExitAction.RESTART
        # RESTART_SUPERVISOR가 아님을 명시적으로 확인
        assert action != ExitAction.RESTART_SUPERVISOR

    def test_exit_44_with_use_exit_codes_resolves_to_restart_supervisor(self):
        """use_exit_codes=True + exit 44 → RESTART_SUPERVISOR"""
        pm = ProcessManager()
        action = pm.resolve_exit_action(44)
        assert action == ExitAction.RESTART_SUPERVISOR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
