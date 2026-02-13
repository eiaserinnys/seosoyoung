"""SessionMonitor 단위 테스트 - 봇 자식 프로세스 기반 감지"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psutil
import pytest

from supervisor.session_monitor import SessionMonitor


def _make_pm(bot_pid: int | None = None) -> MagicMock:
    """봇 PID가 설정된 모의 ProcessManager를 생성."""
    pm = MagicMock()
    pm.get_pid.return_value = bot_pid
    return pm


def _make_child(pid: int, name: str) -> MagicMock:
    """모의 psutil 자식 프로세스 생성."""
    child = MagicMock()
    child.pid = pid
    child.name.return_value = name
    return child


@pytest.fixture
def pm_running():
    """봇이 실행 중인 ProcessManager."""
    return _make_pm(bot_pid=1000)


@pytest.fixture
def pm_stopped():
    """봇이 정지된 ProcessManager."""
    return _make_pm(bot_pid=None)


class TestBotStopped:
    def test_safe_when_bot_stopped(self, pm_stopped):
        """봇이 정지 상태면 세션 0, 배포 안전"""
        monitor = SessionMonitor(pm_stopped)
        assert monitor.active_session_count() == 0
        assert monitor.is_safe_to_deploy() is True

    def test_safe_when_bot_not_registered(self):
        """봇이 등록되지 않은 경우에도 안전 (get_pid가 None 반환)"""
        pm = MagicMock()
        pm.get_pid.return_value = None
        monitor = SessionMonitor(pm)
        assert monitor.is_safe_to_deploy() is True


class TestBotRunningNoSessions:
    def test_no_claude_children(self, pm_running):
        """봇은 실행 중이지만 claude 자식 없음"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                _make_child(2000, "python.exe"),
                _make_child(2001, "node.exe"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 0
            assert monitor.is_safe_to_deploy() is True

    def test_bot_process_disappeared(self, pm_running):
        """봇 PID가 있지만 프로세스가 이미 종료됨 (NoSuchProcess)"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            MockProc.side_effect = psutil.NoSuchProcess(1000)
            assert monitor.active_session_count() == 0
            assert monitor.is_safe_to_deploy() is True


class TestBotRunningWithSessions:
    def test_one_claude_child(self, pm_running):
        """봇의 자식 중 claude.exe 1개"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                _make_child(2000, "python.exe"),
                _make_child(2001, "claude.exe"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 1
            assert monitor.is_safe_to_deploy() is False

    def test_multiple_claude_children(self, pm_running):
        """봇의 자식 중 claude.exe 여러 개"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                _make_child(2001, "claude.exe"),
                _make_child(2002, "claude.exe"),
                _make_child(2003, "node.exe"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 2

    def test_case_insensitive_match(self, pm_running):
        """프로세스 이름 대소문자 무시"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                _make_child(2001, "Claude.EXE"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 1


class TestIgnoresNonBotProcesses:
    def test_ignores_user_claude_desktop(self, pm_running):
        """사용자의 Claude Desktop은 봇 자식이 아니므로 감지하지 않음."""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = []
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 0


class TestCustomBotName:
    def test_custom_bot_name(self):
        """bot_name 커스텀 값 사용"""
        pm = MagicMock()
        pm.get_pid.return_value = 5000
        monitor = SessionMonitor(pm, bot_name="my-bot")
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.return_value = [_make_child(5001, "claude.exe")]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 1
        pm.get_pid.assert_called_with("my-bot")


class TestErrorHandling:
    def test_children_access_denied(self, pm_running):
        """children() 호출 시 AccessDenied"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            bot_proc = MagicMock()
            bot_proc.children.side_effect = psutil.AccessDenied(1000)
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 0

    def test_child_name_access_denied(self, pm_running):
        """개별 자식 프로세스 name() 호출 시 AccessDenied"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            denied_child = MagicMock()
            denied_child.pid = 3000
            denied_child.name.side_effect = psutil.AccessDenied(3000)

            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                denied_child,
                _make_child(3001, "claude.exe"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 1

    def test_child_disappeared_during_iteration(self, pm_running):
        """children() 이후 자식이 종료되어 NoSuchProcess 발생"""
        monitor = SessionMonitor(pm_running)
        with patch("supervisor.session_monitor.psutil.Process") as MockProc:
            gone_child = MagicMock()
            gone_child.pid = 4000
            gone_child.name.side_effect = psutil.NoSuchProcess(4000)

            bot_proc = MagicMock()
            bot_proc.children.return_value = [
                gone_child,
                _make_child(4001, "claude.exe"),
            ]
            MockProc.return_value = bot_proc
            assert monitor.active_session_count() == 1

    def test_os_error_returns_zero(self, pm_running):
        """OSError 발생 시 0 반환"""
        monitor = SessionMonitor(pm_running)
        with patch.object(monitor, "_find_bot_child_sessions", side_effect=OSError("fail")):
            assert monitor.active_session_count() == 0
