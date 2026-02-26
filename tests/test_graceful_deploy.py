"""Graceful 배포/재시작 UX 테스트

Phase 1: 커밋 목록 중복 제거
Phase 2: 봇 측 종료 시 세션 대기 팝업
Phase 3: 재시작 완료 메시지 추가
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# supervisor 모듈 임포트를 위한 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# == Phase 1 테스트 ==


class TestPhase1_DeployMessageNoDuplicateCommits:
    """Phase 1: 배포 메시지에서 커밋 목록 중복 제거"""

    def test_format_deploy_start_message_no_params(self):
        """format_deploy_start_message()가 파라미터 없이 호출 가능"""
        from supervisor.notifier import format_deploy_start_message

        result = format_deploy_start_message()
        assert "업데이트합니다" in result
        assert ":arrows_counterclockwise:" in result

    def test_format_deploy_start_message_no_commits(self):
        """배포 시작 메시지에 커밋 해시가 포함되지 않음"""
        from supervisor.notifier import format_deploy_start_message

        result = format_deploy_start_message()
        # 단순 텍스트만 있어야 함
        lines = result.strip().split("\n")
        assert len(lines) == 1

    def test_format_change_detected_has_commits(self):
        """변경점 감지 메시지에는 커밋 목록이 포함됨"""
        from supervisor.notifier import format_change_detected_message

        result = format_change_detected_message(
            runtime_commits=["abc1234 feat: test feature"],
            seosoyoung_commits=[],
        )
        assert "변경점" in result
        assert "`abc1234`" in result
        assert "test feature" in result

    def test_notify_deploy_start_no_git_fetch(self):
        """notify_deploy_start()가 git 커밋 조회를 하지 않음"""
        from supervisor.notifier import notify_deploy_start

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"slackWebhookUrl": "https://hooks.slack.com/test"}, f)
            config_path = Path(f.name)

        try:
            paths = {
                "runtime": Path("/fake/runtime"),
                "workspace": Path("/fake/workspace"),
            }
            with mock.patch(
                "supervisor.notifier.send_webhook"
            ) as mock_send, mock.patch(
                "supervisor.notifier.get_pending_commits"
            ) as mock_commits:
                notify_deploy_start(paths, config_path)

                # send_webhook이 호출됨
                mock_send.assert_called_once()
                # get_pending_commits는 호출되지 않음
                mock_commits.assert_not_called()

                # 메시지에 커밋 정보 없음
                sent_message = mock_send.call_args[0][1]
                assert "업데이트합니다" in sent_message
        finally:
            os.unlink(config_path)

    def test_change_detected_has_commits_deploy_start_does_not(self):
        """변경점 감지에만 커밋 목록, 배포 시작에는 없음"""
        from supervisor.notifier import (
            format_change_detected_message,
            format_deploy_start_message,
        )

        change_msg = format_change_detected_message(
            runtime_commits=["abc1234 feat: something"],
            seosoyoung_commits=["def5678 fix: bug"],
        )
        deploy_msg = format_deploy_start_message()

        # 변경점 감지: 커밋 해시 포함
        assert "`abc1234`" in change_msg
        assert "`def5678`" in change_msg

        # 배포 시작: 커밋 해시 미포함
        assert "abc1234" not in deploy_msg
        assert "def5678" not in deploy_msg


# == Phase 3 테스트 ==


class TestPhase3_RestartMessages:
    """Phase 3: 재시작 완료 메시지 추가"""

    def test_format_restart_start_message(self):
        """재시작 시작 메시지 포맷"""
        from supervisor.notifier import format_restart_start_message

        result = format_restart_start_message()
        assert "재시작" in result
        assert ":arrows_counterclockwise:" in result

    def test_format_restart_complete_message(self):
        """재시작 완료 메시지 포맷"""
        from supervisor.notifier import format_restart_complete_message

        result = format_restart_complete_message()
        assert "재시작" in result
        assert "완료" in result
        assert ":white_check_mark:" in result

    def test_notify_restart_start(self):
        """notify_restart_start()가 웹훅을 올바르게 전송"""
        from supervisor.notifier import notify_restart_start

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"slackWebhookUrl": "https://hooks.slack.com/test"}, f)
            config_path = Path(f.name)

        try:
            with mock.patch("supervisor.notifier.send_webhook") as mock_send:
                notify_restart_start(config_path)
                mock_send.assert_called_once()
                sent_message = mock_send.call_args[0][1]
                assert "재시작" in sent_message
        finally:
            os.unlink(config_path)

    def test_notify_restart_complete(self):
        """notify_restart_complete()가 웹훅을 올바르게 전송"""
        from supervisor.notifier import notify_restart_complete

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"slackWebhookUrl": "https://hooks.slack.com/test"}, f)
            config_path = Path(f.name)

        try:
            with mock.patch("supervisor.notifier.send_webhook") as mock_send:
                notify_restart_complete(config_path)
                mock_send.assert_called_once()
                sent_message = mock_send.call_args[0][1]
                assert "재시작" in sent_message
                assert "완료" in sent_message
        finally:
            os.unlink(config_path)

    def test_restart_marker_create_and_check(self):
        """재시작 마커 파일 생성 및 확인"""
        from supervisor.deployer import Deployer, _RESTART_MARKER_NAME

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir) / "runtime"
            data_dir = runtime / "data"
            data_dir.mkdir(parents=True)

            webhook_config = data_dir / "watchdog_config.json"
            webhook_config.write_text(
                json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
                encoding="utf-8",
            )

            paths = {
                "runtime": runtime,
                "workspace": Path(tmpdir) / "workspace",
            }

            mock_pm = mock.MagicMock()
            mock_sm = mock.MagicMock()

            deployer = Deployer(mock_pm, mock_sm, paths)

            # 마커 파일 생성
            deployer._create_restart_marker()
            marker = data_dir / _RESTART_MARKER_NAME
            assert marker.exists()

            # 마커 확인 및 완료 알림
            with mock.patch("supervisor.notifier.send_webhook") as mock_send:
                deployer.check_and_notify_restart_complete()

                # 마커가 삭제됨
                assert not marker.exists()

                # 재시작 완료 웹훅이 전송됨
                mock_send.assert_called_once()
                sent_message = mock_send.call_args[0][1]
                assert "재시작" in sent_message
                assert "완료" in sent_message

    def test_no_marker_no_notification(self):
        """마커 파일이 없으면 재시작 완료 알림을 보내지 않음"""
        from supervisor.deployer import Deployer

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir) / "runtime"
            data_dir = runtime / "data"
            data_dir.mkdir(parents=True)

            webhook_config = data_dir / "watchdog_config.json"
            webhook_config.write_text(
                json.dumps({"slackWebhookUrl": "https://hooks.slack.com/test"}),
                encoding="utf-8",
            )

            paths = {
                "runtime": runtime,
                "workspace": Path(tmpdir) / "workspace",
            }

            mock_pm = mock.MagicMock()
            mock_sm = mock.MagicMock()

            deployer = Deployer(mock_pm, mock_sm, paths)

            with mock.patch("supervisor.notifier.send_webhook") as mock_send:
                deployer.check_and_notify_restart_complete()
                mock_send.assert_not_called()


# == 통합 시나리오 테스트 ==


class TestDeployMessageFlow:
    """배포 메시지 흐름 전체 확인"""

    def test_deploy_flow_messages(self):
        """정상 배포 시 메시지 순서: 업데이트합니다 -> 재시작 중 -> 재시작 완료"""
        from supervisor.notifier import (
            format_deploy_start_message,
            format_restart_start_message,
            format_restart_complete_message,
        )

        messages = [
            format_deploy_start_message(),
            format_restart_start_message(),
            format_restart_complete_message(),
        ]

        assert "업데이트합니다" in messages[0]
        assert "재시작 중" in messages[1] or "재시작" in messages[1]
        assert "완료" in messages[2]

    def test_no_duplicate_commits_in_flow(self):
        """커밋 목록은 변경점 감지에만, 배포 시작/재시작에는 없음"""
        from supervisor.notifier import (
            format_change_detected_message,
            format_deploy_start_message,
            format_restart_start_message,
            format_restart_complete_message,
        )

        commits = ["abc1234 feat: important change"]
        change_msg = format_change_detected_message(commits, [])
        deploy_msg = format_deploy_start_message()
        restart_msg = format_restart_start_message()
        complete_msg = format_restart_complete_message()

        # 커밋은 변경점 감지에만
        assert "`abc1234`" in change_msg
        assert "abc1234" not in deploy_msg
        assert "abc1234" not in restart_msg
        assert "abc1234" not in complete_msg
