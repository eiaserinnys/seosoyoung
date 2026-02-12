"""GitPoller 단위 테스트"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from supervisor.git_poller import GitPoller


@pytest.fixture
def poller(tmp_path):
    return GitPoller(repo_path=tmp_path, remote="origin", branch="main")


class TestInit:
    def test_defaults(self, tmp_path):
        p = GitPoller(repo_path=tmp_path)
        assert p.repo_path == tmp_path
        assert p.remote == "origin"
        assert p.branch == "main"

    def test_custom(self, tmp_path):
        p = GitPoller(repo_path=tmp_path, remote="upstream", branch="dev")
        assert p.remote == "upstream"
        assert p.branch == "dev"


class TestCheck:
    def test_returns_true_when_heads_differ(self, poller):
        """원격과 로컬 HEAD가 다르면 True"""
        with patch.object(poller, "_fetch") as mock_fetch, \
             patch.object(poller, "_rev_parse", side_effect=["aaa111", "bbb222"]):
            result = poller.check()
            assert result is True
            mock_fetch.assert_called_once()

    def test_returns_false_when_heads_match(self, poller):
        """원격과 로컬 HEAD가 같으면 False"""
        with patch.object(poller, "_fetch"), \
             patch.object(poller, "_rev_parse", side_effect=["aaa111", "aaa111"]):
            result = poller.check()
            assert result is False

    def test_network_error_returns_false(self, poller):
        """네트워크 오류 시 크래시 없이 False 반환"""
        with patch.object(poller, "_fetch", side_effect=subprocess.SubprocessError("network")):
            result = poller.check()
            assert result is False

    def test_stores_heads_after_check(self, poller):
        """check 후 local_head, remote_head 속성이 갱신"""
        with patch.object(poller, "_fetch"), \
             patch.object(poller, "_rev_parse", side_effect=["local123", "remote456"]):
            poller.check()
            assert poller.local_head == "local123"
            assert poller.remote_head == "remote456"


class TestFetch:
    def test_fetch_calls_git(self, poller):
        """_fetch가 git fetch를 호출"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            poller._fetch()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[:2] == ["git", "fetch"]

    def test_fetch_raises_on_failure(self, poller):
        """fetch 실패 시 SubprocessError"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stderr="fatal: error")
            with pytest.raises(subprocess.SubprocessError):
                poller._fetch()


class TestRevParse:
    def test_rev_parse_local(self, poller):
        """로컬 HEAD 파싱"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
            result = poller._rev_parse("HEAD")
            assert result == "abc123"

    def test_rev_parse_remote(self, poller):
        """원격 HEAD 파싱"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="def456\n")
            result = poller._rev_parse("origin/main")
            assert result == "def456"


class TestReset:
    def test_reset_clears_heads(self, poller):
        """reset 후 head 값 초기화"""
        with patch.object(poller, "_fetch"), \
             patch.object(poller, "_rev_parse", side_effect=["aaa", "bbb"]):
            poller.check()
        poller.reset()
        assert poller.local_head is None
        assert poller.remote_head is None
