"""mention.py의 파일 첨부 다운로드 실패 피드백 테스트

create_session_and_run_claude에서 파일 첨부가 있었으나 다운로드 결과가 비어
있을 때 사용자에게 안내 메시지를 보내는지 검증한다.
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_deps(**overrides):
    """테스트용 dependencies 딕셔너리 생성"""
    defaults = {
        "session_manager": MagicMock(),
        "restart_manager": MagicMock(is_pending=False),
        "run_claude_in_session": MagicMock(),
        "check_permission": MagicMock(return_value=True),
        "get_user_role": MagicMock(
            return_value={
                "username": "tester",
                "role": "admin",
                "user_id": "U_USER",
                "allowed_tools": [],
            }
        ),
        "get_running_session_count": MagicMock(return_value=0),
        "send_restart_confirmation": MagicMock(),
        "list_runner_ref": MagicMock(return_value=None),
        "channel_store": None,
        "channel_collector": None,
        "channel_observer": None,
        "channel_compressor": None,
        "channel_cooldown": None,
        "update_message_fn": MagicMock(),
    }
    defaults.update(overrides)
    return defaults


class TestMentionFileAttachmentFailureFeedback:
    """파일 첨부 다운로드 실패 시 사용자 안내"""

    @patch("seosoyoung.slackbot.handlers.mention._get_channel_messages", return_value=[])
    @patch("seosoyoung.slackbot.handlers.mention.Config")
    def test_download_empty_with_empty_text_triggers_feedback(
        self, mock_config, mock_get_msgs
    ):
        """텍스트 없음 + 파일 첨부 있음 + 다운로드 결과 비어있음
        → 안내 메시지 + return (run_claude 호출 안함)
        """
        mock_config.CHANNEL_OBSERVER_CHANNELS = []

        from seosoyoung.slackbot.handlers.mention import create_session_and_run_claude

        mock_session = MagicMock(
            source_type="thread", last_seen_ts="", message_count=0
        )
        deps = _make_deps()
        deps["session_manager"].create.return_value = mock_session

        event = {
            "user": "U_USER",
            "channel": "C_GEN",
            "text": "",
            "ts": "1234.5678",
            "files": [
                {
                    "id": "F001",
                    "name": "img.png",
                    "mimetype": "image/png",
                    "filetype": "png",
                    "size": 100,
                    "url_private": "https://files.slack.com/img.png",
                }
            ],
        }

        say = MagicMock()
        client = MagicMock()

        # 다운로드 실패(빈 리스트 반환)
        with patch(
            "seosoyoung.slackbot.handlers.mention.download_files_sync",
            return_value=[],
        ):
            create_session_and_run_claude(
                event=event,
                clean_text="",
                channel="C_GEN",
                ts="1234.5678",
                thread_ts=None,
                user_id="U_USER",
                say=say,
                client=client,
                deps=deps,
            )

        # 세션은 생성됨
        deps["session_manager"].create.assert_called_once()

        # 안내 메시지가 사용자에게 발송됨
        say.assert_called_once()
        call_kwargs = say.call_args[1]
        assert "첨부 파일을 가져오지 못하였" in call_kwargs["text"]
        assert call_kwargs["thread_ts"] == "1234.5678"

        # Claude 실행은 호출되지 않음
        deps["run_claude_in_session"].assert_not_called()

    @patch("seosoyoung.slackbot.handlers.mention._get_channel_messages", return_value=[])
    @patch("seosoyoung.slackbot.handlers.mention.Config")
    def test_download_exception_with_empty_text_triggers_feedback(
        self, mock_config, mock_get_msgs
    ):
        """다운로드 중 예외 발생 + 텍스트 없음 → 안내 + return"""
        mock_config.CHANNEL_OBSERVER_CHANNELS = []

        from seosoyoung.slackbot.handlers.mention import create_session_and_run_claude

        mock_session = MagicMock(
            source_type="thread", last_seen_ts="", message_count=0
        )
        deps = _make_deps()
        deps["session_manager"].create.return_value = mock_session

        event = {
            "user": "U_USER",
            "channel": "C_GEN",
            "text": "",
            "ts": "1234.5678",
            "files": [
                {
                    "id": "F002",
                    "name": "doc.pdf",
                    "mimetype": "application/pdf",
                    "filetype": "pdf",
                    "size": 2048,
                    "url_private": "https://files.slack.com/doc.pdf",
                }
            ],
        }

        say = MagicMock()
        client = MagicMock()

        with patch(
            "seosoyoung.slackbot.handlers.mention.download_files_sync",
            side_effect=RuntimeError("network down"),
        ):
            create_session_and_run_claude(
                event=event,
                clean_text="",
                channel="C_GEN",
                ts="1234.5678",
                thread_ts=None,
                user_id="U_USER",
                say=say,
                client=client,
                deps=deps,
            )

        say.assert_called_once()
        assert "첨부 파일을 가져오지 못하였" in say.call_args[1]["text"]
        deps["run_claude_in_session"].assert_not_called()

    @patch("seosoyoung.slackbot.handlers.mention._get_channel_messages", return_value=[])
    @patch("seosoyoung.slackbot.handlers.mention.Config")
    def test_download_failure_with_text_still_runs(
        self, mock_config, mock_get_msgs
    ):
        """파일 다운로드는 실패했지만 텍스트가 있으면 텍스트만으로 진행"""
        mock_config.CHANNEL_OBSERVER_CHANNELS = []

        from seosoyoung.slackbot.handlers.mention import create_session_and_run_claude

        mock_session = MagicMock(
            source_type="thread", last_seen_ts="", message_count=0
        )
        deps = _make_deps()
        deps["session_manager"].create.return_value = mock_session

        event = {
            "user": "U_USER",
            "channel": "C_GEN",
            "text": "이것 좀 봐주세요",
            "ts": "1234.5678",
            "files": [
                {
                    "id": "F003",
                    "name": "img.png",
                    "mimetype": "image/png",
                    "filetype": "png",
                    "size": 100,
                    "url_private": "https://files.slack.com/img.png",
                }
            ],
        }

        say = MagicMock()
        client = MagicMock()

        with patch(
            "seosoyoung.slackbot.handlers.mention.download_files_sync",
            return_value=[],
        ):
            create_session_and_run_claude(
                event=event,
                clean_text="이것 좀 봐주세요",
                channel="C_GEN",
                ts="1234.5678",
                thread_ts=None,
                user_id="U_USER",
                say=say,
                client=client,
                deps=deps,
            )

        # 텍스트가 있으면 다운로드 실패 안내 없이 Claude 실행이 호출됨
        deps["run_claude_in_session"].assert_called_once()
        # 안내 메시지는 발송되지 않음 (다운로드 실패지만 텍스트로 진행)
        for call in say.call_args_list:
            text = call[1].get("text", "") if call[1] else (call[0][0] if call[0] else "")
            assert "첨부 파일을 가져오지 못하였" not in text

    @patch("seosoyoung.slackbot.handlers.mention._get_channel_messages", return_value=[])
    @patch("seosoyoung.slackbot.handlers.mention.Config")
    def test_download_success_proceeds_with_file_context(
        self, mock_config, mock_get_msgs
    ):
        """다운로드 성공 → file_context가 구성되어 Claude 실행"""
        mock_config.CHANNEL_OBSERVER_CHANNELS = []

        from seosoyoung.slackbot.handlers.mention import create_session_and_run_claude

        mock_session = MagicMock(
            source_type="thread", last_seen_ts="", message_count=0
        )
        deps = _make_deps()
        deps["session_manager"].create.return_value = mock_session

        event = {
            "user": "U_USER",
            "channel": "C_GEN",
            "text": "",
            "ts": "1234.5678",
            "files": [
                {
                    "id": "F004",
                    "name": "pic.png",
                    "mimetype": "image/png",
                    "filetype": "png",
                    "size": 500,
                    "url_private": "https://files.slack.com/pic.png",
                }
            ],
        }

        say = MagicMock()
        client = MagicMock()

        downloaded = [
            {
                "local_path": "/tmp/pic.png",
                "original_name": "pic.png",
                "size": 500,
                "file_type": "image",
                "content": None,
            }
        ]
        with patch(
            "seosoyoung.slackbot.handlers.mention.download_files_sync",
            return_value=downloaded,
        ):
            create_session_and_run_claude(
                event=event,
                clean_text="",
                channel="C_GEN",
                ts="1234.5678",
                thread_ts=None,
                user_id="U_USER",
                say=say,
                client=client,
                deps=deps,
            )

        # 텍스트 없지만 파일이 성공적으로 다운로드됐으므로 Claude 실행이 호출됨
        deps["run_claude_in_session"].assert_called_once()
        # 다운로드 실패 안내는 없음
        for call in say.call_args_list:
            text = call[1].get("text", "") if call[1] else ""
            assert "첨부 파일을 가져오지 못하였" not in text
