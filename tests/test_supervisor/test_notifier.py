"""Notifier 모듈 단위 테스트"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

from supervisor.notifier import (
    load_webhook_url,
    get_pending_commits,
    format_deploy_start_message,
    format_deploy_success_message,
    format_deploy_failure_message,
    send_webhook,
    notify_deploy_start,
    notify_deploy_success,
    notify_deploy_failure,
)


class TestLoadWebhookUrl:
    def test_loads_url_from_config(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        url = load_webhook_url(config_file)
        assert url == "https://hooks.slack.com/test"

    def test_returns_none_when_file_missing(self, tmp_path):
        url = load_webhook_url(tmp_path / "nonexistent.json")
        assert url is None

    def test_returns_none_when_key_missing(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(json.dumps({"other": "value"}), encoding="utf-8")
        url = load_webhook_url(config_file)
        assert url is None

    def test_returns_none_when_url_empty(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": ""}), encoding="utf-8"
        )
        url = load_webhook_url(config_file)
        assert url is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text("not json", encoding="utf-8")
        url = load_webhook_url(config_file)
        assert url is None


class TestGetPendingCommits:
    def test_returns_commit_lines(self):
        git_output = "a1b2c3d feat: add feature\ne4f5g6h fix: bug fix\n"
        with patch("supervisor.notifier.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=git_output
            )
            commits = get_pending_commits(Path("/repo"))
        assert len(commits) == 2
        assert commits[0] == "a1b2c3d feat: add feature"
        assert commits[1] == "e4f5g6h fix: bug fix"

    def test_returns_empty_on_failure(self):
        with patch("supervisor.notifier.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error"
            )
            commits = get_pending_commits(Path("/repo"))
        assert commits == []

    def test_returns_empty_on_exception(self):
        with patch("supervisor.notifier.subprocess.run", side_effect=OSError("fail")):
            commits = get_pending_commits(Path("/repo"))
        assert commits == []

    def test_filters_empty_lines(self):
        git_output = "a1b2c3d feat: add\n\ne4f5g6h fix: bug\n"
        with patch("supervisor.notifier.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=git_output)
            commits = get_pending_commits(Path("/repo"))
        assert len(commits) == 2


class TestFormatDeployStartMessage:
    def test_with_both_repos(self):
        runtime_commits = ["a1b2c3d feat: runtime change"]
        seosoyoung_commits = ["e4f5g6h fix: bot fix"]
        msg = format_deploy_start_message(runtime_commits, seosoyoung_commits)
        assert ":arrows_counterclockwise:" in msg
        assert "*runtime*" in msg
        assert "`a1b2c3d`" in msg
        assert "runtime change" in msg
        assert "*seosoyoung*" in msg
        assert "`e4f5g6h`" in msg
        assert "bot fix" in msg

    def test_with_only_runtime(self):
        msg = format_deploy_start_message(
            ["a1b2c3d feat: change"], []
        )
        assert "*runtime*" in msg
        assert "*seosoyoung*" not in msg

    def test_with_only_seosoyoung(self):
        msg = format_deploy_start_message(
            [], ["e4f5g6h fix: fix"]
        )
        assert "*seosoyoung*" in msg
        assert "*runtime*" not in msg

    def test_with_no_commits(self):
        msg = format_deploy_start_message([], [])
        assert ":arrows_counterclockwise:" in msg

    def test_truncates_at_10_commits(self):
        commits = [f"{i:07x} commit {i}" for i in range(15)]
        msg = format_deploy_start_message(commits, [])
        assert "... 외 5건" in msg

    def test_exactly_10_commits_no_truncation(self):
        commits = [f"{i:07x} commit {i}" for i in range(10)]
        msg = format_deploy_start_message(commits, [])
        assert "외" not in msg

    def test_commit_hash_format(self):
        """Hash is first 7 chars wrapped in backticks"""
        msg = format_deploy_start_message(
            ["abcdef1234567 long commit message"], []
        )
        assert "`abcdef1`" in msg
        assert "long commit message" in msg


class TestFormatDeploySuccessMessage:
    def test_success_message(self):
        msg = format_deploy_success_message()
        assert ":white_check_mark:" in msg


class TestFormatDeployFailureMessage:
    def test_failure_message_with_error(self):
        msg = format_deploy_failure_message("connection timeout")
        assert ":x:" in msg
        assert "connection timeout" in msg

    def test_failure_message_without_error(self):
        msg = format_deploy_failure_message()
        assert ":x:" in msg


class TestSendWebhook:
    def test_sends_post_request(self):
        with patch("supervisor.notifier.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = MagicMock()
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            send_webhook("https://hooks.slack.com/test", "hello")

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://hooks.slack.com/test"
        assert req.method == "POST"
        body = json.loads(req.data.decode("utf-8"))
        assert body["text"] == "hello"

    def test_silently_fails_on_error(self):
        with patch(
            "supervisor.notifier.urllib.request.urlopen",
            side_effect=Exception("network error"),
        ):
            # Should not raise
            send_webhook("https://hooks.slack.com/test", "hello")


class TestNotifyDeployStart:
    def test_sends_when_url_configured(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        paths = {"runtime": Path("/runtime"), "workspace": Path("/workspace")}

        with patch("supervisor.notifier.get_pending_commits") as mock_commits, \
             patch("supervisor.notifier.send_webhook") as mock_send:
            mock_commits.return_value = ["abc1234 feat: test"]
            notify_deploy_start(paths, config_file)

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert ":arrows_counterclockwise:" in msg

    def test_skips_when_no_url(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        paths = {"runtime": Path("/runtime"), "workspace": Path("/workspace")}

        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_deploy_start(paths, config_file)

        mock_send.assert_not_called()


class TestNotifyDeploySuccess:
    def test_sends_when_url_configured(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_deploy_success(config_file)

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert ":white_check_mark:" in msg

    def test_skips_when_no_url(self, tmp_path):
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_deploy_success(tmp_path / "nonexistent.json")
        mock_send.assert_not_called()


class TestNotifyDeployFailure:
    def test_sends_when_url_configured(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_deploy_failure(config_file, "test error")

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert ":x:" in msg
        assert "test error" in msg

    def test_skips_when_no_url(self, tmp_path):
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_deploy_failure(tmp_path / "nonexistent.json")
        mock_send.assert_not_called()
