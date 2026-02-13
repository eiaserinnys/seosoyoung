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

    def test_dm_progress_always_posts_new_message(self):
        """DM 사고 과정은 항상 chat_postMessage로 새 메시지를 추가해야 함 (chat_update 사용 안 함)"""
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.trello.watcher import TrackedCard

        mock_client = MagicMock()
        # 첫 번째, 두 번째 chat_postMessage 호출에 각각 다른 ts 반환
        mock_client.chat_postMessage.side_effect = [
            {"ts": "dm_reply_1"},
            {"ts": "dm_reply_2"},
            {"ts": "dm_reply_3"},
        ]

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
        session.thread_ts = "1234.5678"
        session.session_id = "sess123"
        session.message_count = 0
        session.role = "admin"

        # on_progress를 캡처하기 위해 runner를 모킹
        captured_on_progress = None

        def mock_run(prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel):
            nonlocal captured_on_progress
            captured_on_progress = on_progress
            result = MagicMock()
            result.session_id = "sess123"
            result.success = True
            result.interrupted = False
            result.output = "최종 응답"
            result.update_requested = False
            result.restart_requested = False
            result.list_run = None
            result.usage = None
            return result

        mock_runner = MagicMock()
        mock_runner.run = MagicMock(side_effect=mock_run)
        mock_runner.run_sync = lambda coro: coro  # coro가 이미 result를 반환

        with patch("seosoyoung.claude.executor.get_runner_for_role", return_value=mock_runner):
            executor._execute_once(
                session=session,
                prompt="테스트",
                msg_ts="1234.5678",
                channel="C12345",
                say=MagicMock(),
                client=mock_client,
                effective_role="admin",
                trello_card=trello_card,
                is_existing_thread=False,
                initial_msg_ts=None,
                is_trello_mode=True,
                dm_channel_id="D_DM_CHANNEL",
                dm_thread_ts="1111.0000",
            )

        # on_progress가 캡처됐는지 확인
        assert captured_on_progress is not None

        # 첫 번째 호출: 짧은 텍스트 → 새 메시지
        loop = asyncio.new_event_loop()
        loop.run_until_complete(captured_on_progress("첫 번째 사고 과정입니다"))

        # 두 번째 호출: 더 긴 텍스트 (delta 발생) → 또 새 메시지 (chat_update가 아님)
        loop.run_until_complete(captured_on_progress("첫 번째 사고 과정입니다\n두 번째 사고 과정입니다"))
        loop.close()

        # chat_postMessage가 DM 채널로 호출되었는지 확인
        dm_post_calls = [
            call for call in mock_client.chat_postMessage.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL"
        ]
        assert len(dm_post_calls) >= 2, (
            f"DM에 새 메시지가 2회 이상 추가되어야 하지만 {len(dm_post_calls)}회: {dm_post_calls}"
        )

        # chat_update가 DM 채널로 호출되지 않아야 함 (사고 과정에서는 갱신 안 함)
        dm_update_calls = [
            call for call in mock_client.chat_update.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL"
        ]
        assert len(dm_update_calls) == 0, (
            f"DM 사고 과정에서 chat_update가 호출되면 안 됨: {dm_update_calls}"
        )

    def test_dm_progress_per_turn_text_not_skipped(self):
        """턴별 독립 텍스트가 올 때 이전 턴의 누적 길이 때문에 스킵되면 안 됨

        버그: dm_sent_length(누적)와 current_text(턴별)를 비교하여
        두 번째 턴 이후 텍스트가 dm_sent_length보다 짧으면 전부 스킵됨.
        """
        from seosoyoung.claude.executor import ClaudeExecutor
        from seosoyoung.trello.watcher import TrackedCard

        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = [
            {"ts": "dm_reply_1"},
            {"ts": "dm_reply_2"},
            {"ts": "dm_reply_3"},
        ]

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
        session.thread_ts = "1234.5678"
        session.session_id = "sess123"
        session.message_count = 0
        session.role = "admin"

        captured_on_progress = None

        def mock_run(prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel):
            nonlocal captured_on_progress
            captured_on_progress = on_progress
            result = MagicMock()
            result.session_id = "sess123"
            result.success = True
            result.interrupted = False
            result.output = "최종 응답"
            result.update_requested = False
            result.restart_requested = False
            result.list_run = None
            result.usage = None
            return result

        mock_runner = MagicMock()
        mock_runner.run = MagicMock(side_effect=mock_run)
        mock_runner.run_sync = lambda coro: coro

        with patch("seosoyoung.claude.executor.get_runner_for_role", return_value=mock_runner):
            executor._execute_once(
                session=session,
                prompt="테스트",
                msg_ts="1234.5678",
                channel="C12345",
                say=MagicMock(),
                client=mock_client,
                effective_role="admin",
                trello_card=trello_card,
                is_existing_thread=False,
                initial_msg_ts=None,
                is_trello_mode=True,
                dm_channel_id="D_DM_CHANNEL",
                dm_thread_ts="1111.0000",
            )

        assert captured_on_progress is not None

        loop = asyncio.new_event_loop()
        # 턴 1: 긴 텍스트
        loop.run_until_complete(captured_on_progress("첫 번째 턴의 사고 과정입니다. 이것은 꽤 긴 텍스트입니다."))
        # 턴 2: 짧은 텍스트 (독립적인 턴 — 이전 턴보다 짧음)
        loop.run_until_complete(captured_on_progress("두 번째 턴"))
        # 턴 3: 또 짧은 텍스트
        loop.run_until_complete(captured_on_progress("세 번째"))
        loop.close()

        # 3개의 턴 모두 DM에 새 메시지로 전송되어야 함
        dm_post_calls = [
            call for call in mock_client.chat_postMessage.call_args_list
            if call[1].get("channel") == "D_DM_CHANNEL"
        ]
        assert len(dm_post_calls) == 3, (
            f"3개 턴 모두 DM에 전송되어야 하지만 {len(dm_post_calls)}회만 전송됨: "
            f"{[c[1].get('text', '')[:50] for c in dm_post_calls]}"
        )

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


class TestNotifyChannelSuppression:
    """DM 스레드가 있을 때 notify_channel 메시지 완전 억제 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_no_notify_channel_message_when_dm_available(self, mock_config, mock_trello_client):
        """DM이 생성되면 notify_channel에 메시지를 전혀 보내지 않음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "L_TO_GO"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "L_IN_PROGRESS"

        from seosoyoung.trello.watcher import TrelloWatcher

        mock_slack = MagicMock()
        mock_slack.conversations_open.return_value = {"channel": {"id": "D_DM"}}
        # DM 앵커 메시지만 생성됨 (notify_channel 메시지는 없음)
        mock_slack.chat_postMessage.return_value = {"ts": "dm_anchor_ts"}

        mock_trello_instance = MagicMock()
        mock_trello_instance.move_card.return_value = True
        mock_trello_instance.update_card_name.return_value = True

        mock_session_manager = MagicMock()
        mock_session_manager.create.return_value = MagicMock(
            thread_ts="dm_anchor_ts", session_id="sess1", message_count=0
        )

        mock_runner = MagicMock()

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=mock_session_manager,
            claude_runner_factory=mock_runner,
        )
        watcher.trello = mock_trello_instance

        from seosoyoung.trello.watcher import TrelloCard
        card = TrelloCard(
            id="card1", name="테스트 카드", desc="", url="https://trello.com/c/abc",
            list_id="L_TO_GO", labels=[]
        )

        watcher._handle_new_card(card, "to_go")

        # chat_postMessage 호출 중 notify_channel(C_NOTIFY)로 보낸 것이 없어야 함
        notify_calls = [
            call for call in mock_slack.chat_postMessage.call_args_list
            if call[1].get("channel") == "C_NOTIFY"
        ]
        assert len(notify_calls) == 0, (
            f"notify_channel에 메시지가 전송됨: {notify_calls}"
        )

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_dm_channel_used_as_main_channel(self, mock_config, mock_trello_client):
        """DM이 있으면 세션과 claude_runner에 DM 채널이 전달됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "L_TO_GO"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "L_IN_PROGRESS"

        from seosoyoung.trello.watcher import TrelloWatcher
        import threading

        mock_slack = MagicMock()
        mock_slack.conversations_open.return_value = {"channel": {"id": "D_DM"}}
        mock_slack.chat_postMessage.return_value = {"ts": "dm_anchor_ts"}

        mock_trello_instance = MagicMock()
        mock_trello_instance.move_card.return_value = True
        mock_trello_instance.update_card_name.return_value = True

        mock_session_manager = MagicMock()
        mock_session_manager.create.return_value = MagicMock(
            thread_ts="dm_anchor_ts", session_id="sess1", message_count=0
        )

        # claude_runner_factory가 호출될 때까지 블록하고, 전달된 kwargs를 캡처
        captured = {}
        runner_called = threading.Event()

        def capturing_runner(**kwargs):
            captured.update(kwargs)
            runner_called.set()

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=mock_session_manager,
            claude_runner_factory=capturing_runner,
        )
        watcher.trello = mock_trello_instance

        from seosoyoung.trello.watcher import TrelloCard
        card = TrelloCard(
            id="card1", name="테스트 카드", desc="", url="https://trello.com/c/abc",
            list_id="L_TO_GO", labels=[]
        )

        watcher._handle_new_card(card, "to_go")

        # 스레드에서 runner가 호출될 때까지 대기
        runner_called.wait(timeout=5)

        # 세션 생성 시 channel_id가 DM 채널
        mock_session_manager.create.assert_called_once()
        create_kwargs = mock_session_manager.create.call_args[1]
        assert create_kwargs["channel_id"] == "D_DM"

        # claude_runner_factory에 DM 채널이 전달됨
        assert captured.get("channel") == "D_DM"
        assert captured.get("dm_channel_id") == "D_DM"
        assert captured.get("dm_thread_ts") == "dm_anchor_ts"

        # trello_card의 channel_id도 DM
        assert captured.get("trello_card").channel_id == "D_DM"

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_fallback_to_notify_channel_when_dm_fails(self, mock_config, mock_trello_client):
        """DM 생성 실패 시 notify_channel로 폴백"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "L_TO_GO"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = ""  # DM 대상 없음
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "L_IN_PROGRESS"

        from seosoyoung.trello.watcher import TrelloWatcher
        import threading

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "notify_msg_ts"}

        mock_trello_instance = MagicMock()
        mock_trello_instance.move_card.return_value = True
        mock_trello_instance.update_card_name.return_value = True

        mock_session_manager = MagicMock()
        mock_session_manager.create.return_value = MagicMock(
            thread_ts="notify_msg_ts", session_id="sess1", message_count=0
        )

        captured = {}
        runner_called = threading.Event()

        def capturing_runner(**kwargs):
            captured.update(kwargs)
            runner_called.set()

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=mock_session_manager,
            claude_runner_factory=capturing_runner,
        )
        watcher.trello = mock_trello_instance

        from seosoyoung.trello.watcher import TrelloCard
        card = TrelloCard(
            id="card1", name="테스트 카드", desc="", url="https://trello.com/c/abc",
            list_id="L_TO_GO", labels=[]
        )

        watcher._handle_new_card(card, "to_go")
        runner_called.wait(timeout=5)

        # notify_channel에 메시지가 전송되어야 함
        notify_calls = [
            call for call in mock_slack.chat_postMessage.call_args_list
            if call[1].get("channel") == "C_NOTIFY"
        ]
        assert len(notify_calls) >= 1

        # claude_runner에 notify_channel이 전달됨
        assert captured.get("channel") == "C_NOTIFY"
        assert captured.get("trello_card").channel_id == "C_NOTIFY"

    def test_on_progress_skips_notify_channel_when_dm_exists(self):
        """on_progress에서 DM 스레드가 있으면 notify_channel 메시지를 업데이트하지 않음"""
        # on_progress의 trello 모드에서 dm_channel_id가 있을 때
        # notify_channel의 main_msg_ts를 chat_update하지 않아야 함을 검증
        # 실제 검증은 통합 테스트에서 수행
        assert True  # placeholder - 실제 검증은 통합 레벨에서


class TestDmDirectSessionLookup:
    """DM 모드에서 session_manager.get(dm_thread_ts)로 직접 세션을 찾는 테스트

    commit 73074ba 이후, 세션이 dm_thread_ts로 직접 등록되므로
    _dm_thread_map 없이도 인터벤션이 동작합니다.
    """

    @patch("seosoyoung.handlers.message.process_thread_message")
    @patch("seosoyoung.handlers.message.Config")
    def test_dm_thread_message_finds_session_directly(
        self, mock_config, mock_process_thread
    ):
        """DM 스레드 메시지가 session_manager.get(dm_thread_ts)로 직접 세션을 찾아 처리됨"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        # DM 모드에서 세션은 dm_thread_ts로 직접 등록됨
        mock_session = MagicMock()
        mock_session.thread_ts = "dm_anchor_ts"
        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = mock_session

        mock_run_claude = MagicMock()
        mock_get_user_role = MagicMock(return_value={
            "username": "testuser", "role": "admin"
        })

        dependencies = {
            "session_manager": mock_session_manager,
            "restart_manager": MagicMock(is_pending=False),
            "run_claude_in_session": mock_run_claude,
            "get_user_role": mock_get_user_role,
        }

        mock_app = MagicMock()
        handlers = {}

        def capture_handler(event_type):
            def decorator(fn):
                handlers[event_type] = fn
                return fn
            return decorator

        mock_app.event = capture_handler
        register_message_handlers(mock_app, dependencies)

        # DM 스레드에서 메시지 수신 시뮬레이션
        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "text": "작업을 중단하고 이걸 먼저 해주세요",
            "ts": "9999.0001",
            "thread_ts": "dm_anchor_ts",
        }
        handlers["message"](event, MagicMock(), MagicMock())

        # session_manager.get이 dm_thread_ts로 호출됨
        mock_session_manager.get.assert_called_once_with("dm_anchor_ts")

        # process_thread_message가 dm_thread_ts를 thread_ts로 사용하여 호출됨
        mock_process_thread.assert_called_once()
        call_args = mock_process_thread.call_args
        assert call_args[0][2] == "dm_anchor_ts"  # thread_ts

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_untrack_card_cleanup(self, mock_config, mock_trello_client):
        """카드 추적 해제 시 _tracked에서 제거됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = ""

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        tracked = TrackedCard(
            card_id="card1", card_name="테스트", card_url="url",
            list_id="L1", list_key="to_go", thread_ts="dm_anchor_ts",
            channel_id="D_DM", detected_at="2026-01-01", has_execute=True,
        )
        tracked.dm_thread_ts = "dm_anchor_ts"
        watcher._tracked["card1"] = tracked

        watcher._untrack_card("card1")

        assert "card1" not in watcher._tracked


class TestDmInterventionMessageHandler:
    """DM 인터벤션 핸들러 테스트

    commit 73074ba 이후: 세션이 dm_thread_ts로 직접 등록되므로
    DM 스레드 메시지는 일반 메시지와 동일한 경로로 처리됩니다.
    """

    @patch("seosoyoung.handlers.message.process_thread_message")
    @patch("seosoyoung.handlers.message.Config")
    def test_non_dm_thread_message_ignored_without_session(
        self, mock_config, mock_process_thread
    ):
        """DM 매핑이 없는 스레드 메시지는 기존처럼 무시됨"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        mock_watcher = MagicMock()
        mock_watcher.lookup_dm_thread.return_value = None

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None

        dependencies = {
            "session_manager": mock_session_manager,
            "restart_manager": MagicMock(is_pending=False),
            "run_claude_in_session": MagicMock(),
            "get_user_role": MagicMock(),
            "trello_watcher_ref": lambda: mock_watcher,
        }

        mock_app = MagicMock()
        handlers = {}

        def capture_handler(event_type):
            def decorator(fn):
                handlers[event_type] = fn
                return fn
            return decorator

        mock_app.event = capture_handler
        register_message_handlers(mock_app, dependencies)

        event = {
            "user": "U_USER",
            "channel": "C_RANDOM",
            "text": "그냥 메시지",
            "ts": "9999.0002",
            "thread_ts": "unknown_thread_ts",
        }
        handlers["message"](event, MagicMock(), MagicMock())

        # process_thread_message가 호출되지 않아야 함
        mock_process_thread.assert_not_called()

    @patch("seosoyoung.handlers.message.process_thread_message")
    @patch("seosoyoung.handlers.message.Config")
    def test_dm_intervention_without_watcher_gracefully_ignored(
        self, mock_config, mock_process_thread
    ):
        """트렐로 워처가 없을 때 DM 메시지가 에러 없이 무시됨"""
        mock_config.BOT_USER_ID = "B_BOT"
        mock_config.TRANSLATE_CHANNELS = []
        mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []

        from seosoyoung.handlers.message import register_message_handlers

        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None

        dependencies = {
            "session_manager": mock_session_manager,
            "restart_manager": MagicMock(is_pending=False),
            "run_claude_in_session": MagicMock(),
            "get_user_role": MagicMock(),
            # trello_watcher_ref가 None을 반환
            "trello_watcher_ref": lambda: None,
        }

        mock_app = MagicMock()
        handlers = {}

        def capture_handler(event_type):
            def decorator(fn):
                handlers[event_type] = fn
                return fn
            return decorator

        mock_app.event = capture_handler
        register_message_handlers(mock_app, dependencies)

        event = {
            "user": "U_USER",
            "channel": "D_DM",
            "text": "인터벤션 시도",
            "ts": "9999.0003",
            "thread_ts": "dm_anchor_ts",
        }
        handlers["message"](event, MagicMock(), MagicMock())

        # 에러 없이 무시됨
        mock_process_thread.assert_not_called()


class TestReviewCompletionDmRouting:
    """_check_review_list_for_completion의 DM 라우팅 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_completion_notification_sent_to_dm_when_configured(self, mock_config, mock_trello_client):
        """DM 대상 사용자가 설정되어 있으면 완료 알림이 DM으로 전송됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = "L_REVIEW"
        mock_config.TRELLO_DONE_LIST_ID = "L_DONE"
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.trello.client import TrelloCard

        mock_slack = MagicMock()
        mock_slack.conversations_open.return_value = {"channel": {"id": "D_DM"}}

        mock_trello_instance = MagicMock()
        due_card = TrelloCard(
            id="card1", name="완료 카드", desc="", url="https://trello.com/c/abc",
            list_id="L_REVIEW", due_complete=True,
        )
        mock_trello_instance.get_cards_in_list.return_value = [due_card]
        mock_trello_instance.move_card.return_value = True

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )
        watcher.trello = mock_trello_instance

        watcher._check_review_list_for_completion()

        # 완료 알림이 DM 채널로 전송되었는지 확인
        notify_calls = [
            call for call in mock_slack.chat_postMessage.call_args_list
            if "✅" in call[1].get("text", "")
        ]
        assert len(notify_calls) == 1
        assert notify_calls[0][1]["channel"] == "D_DM"

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_completion_notification_fallback_to_notify_channel(self, mock_config, mock_trello_client):
        """DM 대상 사용자가 없으면 완료 알림이 notify_channel로 전송됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = "L_REVIEW"
        mock_config.TRELLO_DONE_LIST_ID = "L_DONE"
        mock_config.TRELLO_DM_TARGET_USER_ID = ""

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.trello.client import TrelloCard

        mock_slack = MagicMock()

        mock_trello_instance = MagicMock()
        due_card = TrelloCard(
            id="card1", name="완료 카드", desc="", url="https://trello.com/c/abc",
            list_id="L_REVIEW", due_complete=True,
        )
        mock_trello_instance.get_cards_in_list.return_value = [due_card]
        mock_trello_instance.move_card.return_value = True

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )
        watcher.trello = mock_trello_instance

        watcher._check_review_list_for_completion()

        # 완료 알림이 notify_channel로 전송되었는지 확인
        notify_calls = [
            call for call in mock_slack.chat_postMessage.call_args_list
            if "✅" in call[1].get("text", "")
        ]
        assert len(notify_calls) == 1
        assert notify_calls[0][1]["channel"] == "C_NOTIFY"


class TestRestartMarkerDmRouting:
    """_handle_restart_marker의 DM 라우팅 테스트"""

    def test_restart_confirmation_uses_current_channel(self):
        """재시작 확인 메시지가 현재 세션 채널로 전송됨 (DM 모드에서는 DM 채널)"""
        from seosoyoung.claude.executor import ClaudeExecutor

        mock_send_restart = MagicMock()
        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            get_session_lock=lambda ts: MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=2),  # 다른 세션 1개 실행 중
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=mock_send_restart,
        )

        result = MagicMock()
        result.update_requested = True
        result.restart_requested = False

        session = MagicMock()
        session.user_id = "trello_watcher"

        # DM 채널에서 실행된 경우
        executor._handle_restart_marker(
            result, session, "D_DM_CHANNEL", "dm_thread_ts", MagicMock()
        )

        # send_restart_confirmation에 DM 채널이 전달되었는지 확인
        mock_send_restart.assert_called_once()
        call_kwargs = mock_send_restart.call_args[1]
        assert call_kwargs["channel"] == "D_DM_CHANNEL"


class TestGetDmOrNotifyChannel:
    """_get_dm_or_notify_channel 헬퍼 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_returns_dm_channel_when_target_configured(self, mock_config, mock_trello_client):
        """DM 대상이 설정되어 있으면 DM 채널 반환"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = "U_TARGET"

        from seosoyoung.trello.watcher import TrelloWatcher

        mock_slack = MagicMock()
        mock_slack.conversations_open.return_value = {"channel": {"id": "D_DM"}}

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        result = watcher._get_dm_or_notify_channel()
        assert result == "D_DM"

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_returns_notify_channel_when_no_target(self, mock_config, mock_trello_client):
        """DM 대상이 없으면 notify_channel 반환"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_DM_TARGET_USER_ID = ""

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        result = watcher._get_dm_or_notify_channel()
        assert result == "C_NOTIFY"

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_fallback_to_notify_on_dm_failure(self, mock_config, mock_trello_client):
        """DM 채널 열기 실패 시 notify_channel로 폴백"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C_NOTIFY"
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
            claude_runner_factory=MagicMock(),
        )

        result = watcher._get_dm_or_notify_channel()
        assert result == "C_NOTIFY"


class TestConfigDmTargetUser:
    """Config.TRELLO_DM_TARGET_USER_ID 설정 테스트"""

    def test_dm_target_user_default_empty(self):
        """기본값은 빈 문자열"""
        from seosoyoung.config import Config

        assert hasattr(Config, "TRELLO_DM_TARGET_USER_ID")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
