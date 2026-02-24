"""supervisor 메인 루프 - 봇 exit 43 → supervisor 전체 재시작 테스트"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from supervisor.models import (
    ExitAction,
    EXIT_CODE_ACTIONS,
    ProcessConfig,
    ProcessState,
    ProcessStatus,
    RestartPolicy,
)


def _make_bot_config() -> ProcessConfig:
    return ProcessConfig(
        name="bot",
        command="python",
        args=["-m", "seosoyoung.slackbot.main"],
        restart_policy=RestartPolicy(use_exit_codes=True, auto_restart=True),
    )


def _make_mcp_config(name: str = "mcp-seosoyoung") -> ProcessConfig:
    return ProcessConfig(
        name=name,
        command="python",
        args=["-m", "some_mcp"],
        restart_policy=RestartPolicy(use_exit_codes=False, auto_restart=True),
    )


class TestExitCodeMapping:
    """exit code → ExitAction 매핑 확인"""

    def test_exit_43_resolves_to_restart(self):
        assert EXIT_CODE_ACTIONS.get(43) == ExitAction.RESTART

    def test_exit_42_resolves_to_update(self):
        assert EXIT_CODE_ACTIONS.get(42) == ExitAction.UPDATE

    def test_exit_0_resolves_to_shutdown(self):
        assert EXIT_CODE_ACTIONS.get(0) == ExitAction.SHUTDOWN


class TestRestartPolicyDistinction:
    """use_exit_codes 플래그에 따른 분기 확인"""

    def test_bot_uses_exit_codes(self):
        bot = _make_bot_config()
        assert bot.restart_policy.use_exit_codes is True

    def test_mcp_does_not_use_exit_codes(self):
        mcp = _make_mcp_config()
        assert mcp.restart_policy.use_exit_codes is False


class TestMainLoopRestartBehavior:
    """메인 루프에서 봇 exit 43 처리 시 supervisor 전체 재시작 검증.

    __main__.py의 핵심 분기 로직을 직접 시뮬레이션한다.
    """

    def _simulate_exit_handling(
        self, name: str, exit_code: int, policy: RestartPolicy
    ) -> str:
        """메인 루프의 exit code 처리 로직을 시뮬레이션.

        Returns:
            "supervisor_exit_43" | "supervisor_exit_42" | "restart" |
            "restart_delay" | "shutdown" | "deployer_update"
        """
        # 액션 결정 (메인 루프의 if/elif 분기 복제)
        if policy.use_exit_codes:
            action = EXIT_CODE_ACTIONS.get(exit_code, ExitAction.RESTART_DELAY)
        elif policy.auto_restart:
            action = ExitAction.RESTART_DELAY
        else:
            action = ExitAction.SHUTDOWN

        # 액션 실행 (메인 루프의 if/elif 분기 복제)
        if action == ExitAction.SHUTDOWN:
            return "shutdown"
        elif action == ExitAction.UPDATE:
            return "deployer_update"
        elif action == ExitAction.RESTART:
            # 핵심 변경: use_exit_codes=True이면 supervisor 전체 재시작
            if policy.use_exit_codes:
                return "supervisor_exit_43"
            return "restart"
        elif action == ExitAction.RESTART_DELAY:
            return "restart_delay"
        return "unknown"

    def test_bot_exit_43_triggers_supervisor_restart(self):
        """봇 exit 43 → supervisor 전체 exit 43"""
        bot = _make_bot_config()
        result = self._simulate_exit_handling("bot", 43, bot.restart_policy)
        assert result == "supervisor_exit_43"

    def test_bot_exit_42_triggers_deployer_update(self):
        """봇 exit 42 → deployer 업데이트 (기존 동작)"""
        bot = _make_bot_config()
        result = self._simulate_exit_handling("bot", 42, bot.restart_policy)
        assert result == "deployer_update"

    def test_bot_exit_0_shutdown(self):
        """봇 exit 0 → 정상 종료"""
        bot = _make_bot_config()
        result = self._simulate_exit_handling("bot", 0, bot.restart_policy)
        assert result == "shutdown"

    def test_mcp_exit_43_does_not_trigger_supervisor_restart(self):
        """MCP exit 43 → 단순 지연 재시작 (supervisor 재시작 아님)"""
        mcp = _make_mcp_config()
        result = self._simulate_exit_handling("mcp-seosoyoung", 43, mcp.restart_policy)
        assert result == "restart_delay"

    def test_mcp_exit_0_also_restart_delay(self):
        """MCP exit 0 → auto_restart이므로 지연 재시작"""
        mcp = _make_mcp_config()
        result = self._simulate_exit_handling("mcp-seosoyoung", 0, mcp.restart_policy)
        assert result == "restart_delay"

    def test_bot_unknown_exit_code_restart_delay(self):
        """봇의 알 수 없는 exit code → 지연 재시작"""
        bot = _make_bot_config()
        result = self._simulate_exit_handling("bot", 99, bot.restart_policy)
        assert result == "restart_delay"


class TestWatchdogCompatibility:
    """watchdog.ps1의 exit 43 처리와 호환되는지 확인.

    watchdog는 exit 43을 받으면:
    - consecutiveFailures = 0 (리셋)
    - 즉시 재시작 (대기 없음, git pull 없음)
    """

    def test_exit_43_is_distinct_from_42(self):
        """exit 42(업데이트)와 43(재시작)은 watchdog에서 다르게 처리됨"""
        # 42: git pull + pip install + 재시작
        # 43: 즉시 재시작 (git pull 없음)
        assert EXIT_CODE_ACTIONS[42] != EXIT_CODE_ACTIONS[43]
        assert EXIT_CODE_ACTIONS[42] == ExitAction.UPDATE
        assert EXIT_CODE_ACTIONS[43] == ExitAction.RESTART
