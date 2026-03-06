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
    format_change_detected_message,
    format_waiting_sessions_message,
    notify_change_detected,
    notify_waiting_sessions,
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
    """format_deploy_start_message() takes no arguments and returns a simple
    deploy-start banner.  Commit details are now in format_change_detected_message."""

    def test_returns_string(self):
        msg = format_deploy_start_message()
        assert isinstance(msg, str)

    def test_contains_emoji(self):
        msg = format_deploy_start_message()
        assert ":arrows_counterclockwise:" in msg


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


class TestFormatChangeDetectedMessage:
    def test_with_multiple_repos(self):
        commits_by_repo = {
            "runtime": ["a1b2c3d feat: runtime change"],
            "seosoyoung": ["e4f5g6h fix: bot fix"],
        }
        msg = format_change_detected_message(commits_by_repo)
        assert ":mag:" in msg
        assert "변경점" in msg
        assert "*runtime*" in msg
        assert "`a1b2c3d`" in msg
        assert "*seosoyoung*" in msg
        assert "`e4f5g6h`" in msg

    def test_with_no_commits(self):
        msg = format_change_detected_message({})
        assert ":mag:" in msg

    def test_with_only_runtime(self):
        msg = format_change_detected_message({
            "runtime": ["a1b2c3d feat: change"],
        })
        assert "*runtime*" in msg
        assert "*seosoyoung*" not in msg

    def test_with_four_repos(self):
        """4개 리포 모두 커밋이 있는 경우"""
        commits_by_repo = {
            "runtime": ["a1b2c3d feat: runtime"],
            "seosoyoung": ["e4f5g6h fix: bot"],
            "seosoyoung-plugins": ["1234567 feat: plugin"],
            "soulstream": ["abcdef0 fix: soul"],
        }
        msg = format_change_detected_message(commits_by_repo)
        assert "*runtime*" in msg
        assert "*seosoyoung*" in msg
        assert "*seosoyoung-plugins*" in msg
        assert "*soulstream*" in msg

    def test_empty_commits_list_excluded(self):
        """빈 커밋 리스트를 가진 리포는 메시지에 포함되지 않음"""
        commits_by_repo = {
            "runtime": ["a1b2c3d feat: change"],
            "seosoyoung": [],
        }
        msg = format_change_detected_message(commits_by_repo)
        assert "*runtime*" in msg
        assert "*seosoyoung*" not in msg


class TestFormatWaitingSessionsMessage:
    def test_contains_hourglass_emoji(self):
        msg = format_waiting_sessions_message()
        assert ":hourglass_flowing_sand:" in msg

    def test_contains_waiting_text(self):
        msg = format_waiting_sessions_message()
        assert "대기" in msg


class TestNotifyChangeDetected:
    def test_sends_when_url_configured(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        repo_paths = {"runtime": runtime}

        with patch("supervisor.notifier.get_pending_commits") as mock_commits, \
             patch("supervisor.notifier.send_webhook") as mock_send:
            mock_commits.return_value = ["abc1234 feat: test"]
            notify_change_detected(repo_paths, config_file)

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert ":mag:" in msg

    def test_skips_when_no_url(self, tmp_path):
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        repo_paths = {"runtime": runtime}

        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_change_detected(repo_paths, tmp_path / "nonexistent.json")

        mock_send.assert_not_called()

    def test_collects_commits_from_all_repos(self, tmp_path):
        """모든 등록된 리포에서 커밋을 수집한다"""
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        runtime = tmp_path / "runtime"
        seosoyoung = tmp_path / "seosoyoung"
        plugins = tmp_path / "plugins"
        soulstream = tmp_path / "soulstream"
        for d in (runtime, seosoyoung, plugins, soulstream):
            d.mkdir()

        repo_paths = {
            "runtime": runtime,
            "seosoyoung": seosoyoung,
            "seosoyoung-plugins": plugins,
            "soulstream": soulstream,
        }

        def fake_commits(path):
            return {
                runtime: ["a1b2c3d feat: runtime change"],
                seosoyoung: ["e4f5g6h fix: bot fix"],
                plugins: ["1234567 feat: plugin update"],
                soulstream: ["abcdef0 fix: soul fix"],
            }.get(path, [])

        with patch("supervisor.notifier.get_pending_commits", side_effect=fake_commits), \
             patch("supervisor.notifier.send_webhook") as mock_send:
            notify_change_detected(repo_paths, config_file)

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert "*runtime*" in msg
        assert "*seosoyoung*" in msg
        assert "*seosoyoung-plugins*" in msg
        assert "*soulstream*" in msg

    def test_skips_nonexistent_repos(self, tmp_path):
        """존재하지 않는 리포 경로는 건너뛴다"""
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        repo_paths = {
            "runtime": runtime,
            "nonexistent": tmp_path / "does_not_exist",
        }

        with patch("supervisor.notifier.get_pending_commits") as mock_commits, \
             patch("supervisor.notifier.send_webhook") as mock_send:
            mock_commits.return_value = ["a1b2c3d feat: test"]
            notify_change_detected(repo_paths, config_file)

        # get_pending_commits는 존재하는 리포에 대해서만 호출
        mock_commits.assert_called_once_with(runtime)

    def test_empty_repos_excluded_from_message(self, tmp_path):
        """커밋이 없는 리포는 메시지에 포함되지 않음"""
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        runtime = tmp_path / "runtime"
        seosoyoung = tmp_path / "seosoyoung"
        runtime.mkdir()
        seosoyoung.mkdir()
        repo_paths = {"runtime": runtime, "seosoyoung": seosoyoung}

        def fake_commits(path):
            if path == runtime:
                return ["a1b2c3d feat: change"]
            return []

        with patch("supervisor.notifier.get_pending_commits", side_effect=fake_commits), \
             patch("supervisor.notifier.send_webhook") as mock_send:
            notify_change_detected(repo_paths, config_file)

        msg = mock_send.call_args[0][1]
        assert "*runtime*" in msg
        assert "*seosoyoung*" not in msg


class TestNotifyWaitingSessions:
    def test_sends_when_url_configured(self, tmp_path):
        config_file = tmp_path / "watchdog_config.json"
        config_file.write_text(
            json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
            encoding="utf-8",
        )
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_waiting_sessions(config_file)

        mock_send.assert_called_once()
        msg = mock_send.call_args[0][1]
        assert ":hourglass_flowing_sand:" in msg

    def test_skips_when_no_url(self, tmp_path):
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_waiting_sessions(tmp_path / "nonexistent.json")
        mock_send.assert_not_called()

    def test_skips_when_config_path_none(self):
        with patch("supervisor.notifier.send_webhook") as mock_send:
            notify_waiting_sessions(None)
        mock_send.assert_not_called()
