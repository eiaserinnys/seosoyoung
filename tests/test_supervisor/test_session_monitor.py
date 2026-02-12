"""SessionMonitor 단위 테스트"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from supervisor.session_monitor import SessionMonitor


@pytest.fixture
def monitor():
    return SessionMonitor()


class TestActiveSessionCount:
    def test_no_sessions(self, monitor):
        """Claude 프로세스 없으면 0"""
        with patch.object(monitor, "_find_claude_processes", return_value=[]):
            assert monitor.active_session_count() == 0

    def test_one_session(self, monitor):
        """Claude 프로세스 1개"""
        procs = [{"pid": 1234, "name": "claude.exe", "cmdline": ["claude"]}]
        with patch.object(monitor, "_find_claude_processes", return_value=procs):
            assert monitor.active_session_count() == 1

    def test_multiple_sessions(self, monitor):
        """Claude 프로세스 여러 개"""
        procs = [
            {"pid": 1234, "name": "claude.exe", "cmdline": ["claude"]},
            {"pid": 5678, "name": "claude.exe", "cmdline": ["claude"]},
            {"pid": 9012, "name": "node.exe", "cmdline": ["node", "claude"]},
        ]
        with patch.object(monitor, "_find_claude_processes", return_value=procs):
            assert monitor.active_session_count() == 3

    def test_process_error_returns_zero(self, monitor):
        """프로세스 조회 실패 시 0"""
        with patch.object(monitor, "_find_claude_processes", side_effect=OSError("access")):
            assert monitor.active_session_count() == 0


class TestIsSafe:
    def test_safe_when_no_sessions(self, monitor):
        """세션 0이면 안전"""
        with patch.object(monitor, "active_session_count", return_value=0):
            assert monitor.is_safe_to_deploy() is True

    def test_unsafe_when_sessions_exist(self, monitor):
        """세션 1 이상이면 안전하지 않음"""
        with patch.object(monitor, "active_session_count", return_value=1):
            assert monitor.is_safe_to_deploy() is False


class TestFindClaudeProcesses:
    def test_finds_claude_exe(self, monitor):
        """claude.exe를 실행 중인 프로세스를 찾음"""
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 100,
            "name": "claude.exe",
            "cmdline": ["C:\\Users\\LG\\AppData\\Local\\Programs\\claude\\claude.exe"],
        }

        with patch("supervisor.session_monitor.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            result = monitor._find_claude_processes()
            assert len(result) == 1
            assert result[0]["pid"] == 100

    def test_finds_claude_code_node(self, monitor):
        """node로 실행된 Claude Code SDK 세션도 찾음"""
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 200,
            "name": "node.exe",
            "cmdline": ["node", "C:\\some\\path\\claude-code\\cli.js"],
        }

        with patch("supervisor.session_monitor.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            result = monitor._find_claude_processes()
            assert len(result) == 1

    def test_ignores_unrelated_processes(self, monitor):
        """무관한 프로세스는 무시"""
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 300,
            "name": "python.exe",
            "cmdline": ["python", "-m", "supervisor"],
        }

        with patch("supervisor.session_monitor.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            result = monitor._find_claude_processes()
            assert len(result) == 0

    def test_handles_access_denied(self, monitor):
        """접근 불가 프로세스는 건너뜀"""
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 400, "name": None, "cmdline": None}

        with patch("supervisor.session_monitor.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            mock_psutil.AccessDenied = PermissionError
            result = monitor._find_claude_processes()
            assert len(result) == 0

    def test_filters_supervisor_own_process(self, monitor):
        """supervisor가 시작한 봇 프로세스는 Claude 세션으로 카운트하지 않음"""
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 500,
            "name": "python.exe",
            "cmdline": ["python", "-m", "seosoyoung.main"],
        }

        with patch("supervisor.session_monitor.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [mock_proc]
            result = monitor._find_claude_processes()
            assert len(result) == 0
