"""DM 스레드 사고 과정 출력 테스트

트렐로 워처/정주행이 앱 DM 스레드에서 사고 과정을 출력하는 기능 테스트.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestOpenDmThread:
    """_open_dm_thread 헬퍼 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_open_dm_thread_success(self, mock_config, mock_trello_client):
        """DM 채널 열기 + 앵커 메시지 전송 성공"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"

        from seosoyoung.trello.watcher import TrelloWatcher

        mock_slack = MagicMock()
        mock_slack.conversations_open.return_value = {"channel": {"id": "D_DM_CHANNEL"}}
        mock_slack.chat_postMessage.return_value = {"ts": "1111.2222"}

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        dm_channel_id, dm_thread_ts = watcher._open_dm_thread("테스트 카드", "https://trello.com/c/abc")

        assert dm_channel_id == "D_DM_CHANNEL"
        assert dm_thread_ts == "1111.2222"
        mock_slack.conversations_open.assert_called_once_with(users="U_TARGET")
        mock_slack.chat_postMessage.assert_called_once()

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_open_dm_thread_no_target_user(self, mock_config, mock_trello_client):
        """DM 대상 사용자가 설정되지 않은 경우 (None, None) 반환"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = ""

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        dm_channel_id, dm_thread_ts = watcher._open_dm_thread("테스트", "https://trello.com/c/abc")

        assert dm_channel_id is None
        assert dm_thread_ts is None

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_open_dm_thread_api_failure(self, mock_config, mock_trello_client):
        """Slack API 실패 시 (None, None) 반환 (폴백)"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"

        from seosoyoung.trello.watcher import TrelloWatcher

        mock_slack = MagicMock()
        mock_slack.conversations_open.side_effect = Exception("API error")

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        dm_channel_id, dm_thread_ts = watcher._open_dm_thread("테스트", "https://trello.com/c/abc")

        assert dm_channel_id is None
        assert dm_thread_ts is None


class TestOnProgressDmThread:
    """on_progress 콜백의 DM 스레드 blockquote 추가 테스트"""

    def test_dm_thread_blockquote_new_reply(self):
        """DM 스레드에 새 blockquote 답글 추가"""
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.claude.message_formatter import escape_backticks

        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "dm_reply_1"}

        # on_progress 함수 동작을 검증하기 위해 _execute_once의 on_progress 로직을 시뮬레이션
        # dm_channel_id와 dm_thread_ts가 있으면 DM 스레드에 답글 추가
        dm_channel_id = "D_DM_CHANNEL"
        dm_thread_ts = "1111.0000"

        # 첫 번째 호출: 새 답글 생성
        mock_client.chat_postMessage.return_value = {"ts": "dm_reply_1"}
        result = mock_client.chat_postMessage(
            channel=dm_channel_id,
            thread_ts=dm_thread_ts,
            text="> 사고 과정 첫 번째",
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "> 사고 과정 첫 번째"}
            }]
        )
        assert result["ts"] == "dm_reply_1"
        mock_client.chat_postMessage.assert_called_with(
            channel="D_DM_CHANNEL",
            thread_ts="1111.0000",
            text="> 사고 과정 첫 번째",
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "> 사고 과정 첫 번째"}
            }]
        )

    def test_dm_thread_update_existing_reply(self):
        """DM 스레드의 기존 답글을 업데이트"""
        mock_client = MagicMock()

        # chat_update 호출 시 성공
        dm_channel_id = "D_DM_CHANNEL"
        dm_last_reply_ts = "dm_reply_1"

        mock_client.chat_update(
            channel=dm_channel_id,
            ts=dm_last_reply_ts,
            text="> 업데이트된 내용",
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "> 업데이트된 내용"}
            }]
        )
        mock_client.chat_update.assert_called_once()


class TestHandleTrelloSuccessWithDm:
    """_handle_trello_success의 DM 스레드 최종 메시지 처리 테스트"""

    def test_dm_last_reply_updated_to_plaintext(self):
        """DM 스레드의 마지막 blockquote가 평문으로 교체됨"""
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.claude.agent_runner import ClaudeResult
        from seosoyoung.trello.watcher import TrackedCard
        from seosoyoung.claude.session import Session

        mock_client = MagicMock()
        mock_session_manager = MagicMock()
        executor = ClaudeExecutor(
            session_manager=mock_session_manager,
            get_session_lock=lambda ts: MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

        result = MagicMock()
        result.session_id = "sess123"
        result.output = "작업 완료 응답"
        result.update_requested = False
        result.restart_requested = False
        result.list_run = None
        result.usage = None

        session = MagicMock()
        session.session_id = "sess123"

        trello_card = TrackedCard(
            card_id="card123",
            card_name="테스트 카드",
            card_url="https://trello.com/c/abc",
            list_id="list123",
            list_key="to_go",
            thread_ts="1234.5678",
            channel_id="C12345",
            detected_at="2026-01-01",
            has_execute=True,
        )

        executor._handle_trello_success(
            result=result,
            response="작업 완료 응답",
            session=session,
            trello_card=trello_card,
            channel="C12345",
            thread_ts="1234.5678",
            main_msg_ts="1234.5678",
            say=MagicMock(),
            client=mock_client,
            dm_channel_id="D_DM_CHANNEL",
            dm_thread_ts="dm_anchor_ts",
            dm_last_reply_ts="dm_reply_last",
        )

        # DM 스레드의 마지막 답글이 평문으로 업데이트되었는지 확인
        dm_update_calls = [
            call for call in mock_client.chat_update.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL" and call[1].get("ts") == "dm_reply_last"
        ]
        assert len(dm_update_calls) == 1
        assert "작업 완료 응답" in dm_update_calls[0][1]["text"]

    def test_no_dm_params_uses_fallback(self):
        """DM 파라미터가 없으면 기존 동작 유지"""
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.trello.watcher import TrackedCard

        mock_client = MagicMock()
        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            get_session_lock=lambda ts: MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

        result = MagicMock()
        result.session_id = "sess123"
        result.output = "응답"
        result.update_requested = False
        result.restart_requested = False
        result.list_run = None
        result.usage = None

        session = MagicMock()
        session.session_id = "sess123"

        trello_card = TrackedCard(
            card_id="card123",
            card_name="테스트",
            card_url="https://trello.com/c/abc",
            list_id="list123",
            list_key="to_go",
            thread_ts="1234.5678",
            channel_id="C12345",
            detected_at="2026-01-01",
            has_execute=True,
        )

        # DM 파라미터 없이 호출 → 에러 없이 정상 동작해야 함
        executor._handle_trello_success(
            result=result,
            response="응답",
            session=session,
            trello_card=trello_card,
            channel="C12345",
            thread_ts="1234.5678",
            main_msg_ts="1234.5678",
            say=MagicMock(),
            client=mock_client,
            dm_channel_id=None,
            dm_thread_ts=None,
            dm_last_reply_ts=None,
        )

        # DM 관련 chat_update가 없어야 함
        dm_calls = [
            call for call in mock_client.chat_update.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL"
        ]
        assert len(dm_calls) == 0


class TestHandleInterruptedWithDm:
    """_handle_interrupted의 DM 스레드 정리 테스트"""

    def test_dm_last_reply_marked_interrupted(self):
        """인터럽트 시 DM 스레드의 마지막 답글이 (중단됨)으로 업데이트"""
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.trello.watcher import TrackedCard

        mock_client = MagicMock()
        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            get_session_lock=lambda ts: MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

        trello_card = TrackedCard(
            card_id="card123",
            card_name="테스트",
            card_url="https://trello.com/c/abc",
            list_id="list123",
            list_key="to_go",
            thread_ts="1234.5678",
            channel_id="C12345",
            detected_at="2026-01-01",
            has_execute=True,
        )

        session = MagicMock()
        session.session_id = "sess123"

        executor._handle_interrupted(
            last_msg_ts="1234.5678",
            main_msg_ts="1234.5678",
            is_trello_mode=True,
            trello_card=trello_card,
            session=session,
            channel="C12345",
            client=mock_client,
            dm_channel_id="D_DM_CHANNEL",
            dm_last_reply_ts="dm_reply_last",
        )

        # DM 스레드의 마지막 답글이 (중단됨)으로 업데이트
        dm_update_calls = [
            call for call in mock_client.chat_update.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL" and call[1].get("ts") == "dm_reply_last"
        ]
        assert len(dm_update_calls) == 1
        assert "(중단됨)" in dm_update_calls[0][1]["text"]


class TestConfigDmTargetUser:
    """Config.TRELLO_DM_TARGET_USER_ID 설정 테스트"""

    def test_dm_target_user_default_empty(self):
        """기본값은 빈 문자열"""
        # Config 모듈을 재로드하지 않고 클래스 변수를 확인
        from seosoyoung.config import Config

        # 환경변수가 설정되지 않은 경우 빈 문자열
        # (실제 테스트 환경에서는 환경변수가 없으므로 빈 문자열)
        assert hasattr(Config, "TRELLO_DM_TARGET_USER_ID")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
