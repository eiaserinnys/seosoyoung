"""TrelloWatcher 테스트"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import threading


class TestTrelloWatcherPauseResume:
    """TrelloWatcher pause/resume 기능 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_initial_not_paused(self, mock_config, mock_trello_client):
        """초기 상태는 일시 중단 아님"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        assert watcher.is_paused is False

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_pause(self, mock_config, mock_trello_client):
        """일시 중단"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        watcher.pause()

        assert watcher.is_paused is True

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_resume(self, mock_config, mock_trello_client):
        """재개"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        watcher.pause()
        assert watcher.is_paused is True

        watcher.resume()
        assert watcher.is_paused is False

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_poll_skipped_when_paused(self, mock_config, mock_trello_client):
        """일시 중단 상태면 폴링 스킵"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_plan": "list123"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 일시 중단
        watcher.pause()

        # 폴링 호출
        watcher._poll()

        # Trello API 호출되지 않아야 함
        mock_trello.get_cards_in_list.assert_not_called()

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_poll_works_when_not_paused(self, mock_config, mock_trello_client):
        """일시 중단 아니면 정상 폴링"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_plan": "list123"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 폴링 호출 (일시 중단 아님)
        watcher._poll()

        # Trello API 호출되어야 함
        mock_trello.get_cards_in_list.assert_called()


class TestTrelloWatcherTrackedCardLookup:
    """TrackedCard 조회 기능 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_get_tracked_by_thread_ts_found(self, mock_config, mock_trello_client):
        """thread_ts로 TrackedCard 조회 - 찾음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # TrackedCard 추가 (To Go 감시용)
        tracked = TrackedCard(
            card_id="card123",
            card_name="테스트 카드",
            card_url="https://trello.com/c/abc123",
            list_id="list123",
            list_key="to_go",
            thread_ts="1234567890.123456",
            channel_id="C12345",
            detected_at="2024-01-01T00:00:00"
        )
        watcher._tracked["card123"] = tracked

        # _register_thread_card 호출하여 _thread_cards에도 등록
        watcher._register_thread_card(tracked)

        # 조회 (이제 _thread_cards에서 조회)
        result = watcher.get_tracked_by_thread_ts("1234567890.123456")
        assert result is not None
        assert result.card_id == "card123"
        assert result.card_name == "테스트 카드"

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_get_tracked_by_thread_ts_not_found(self, mock_config, mock_trello_client):
        """thread_ts로 TrackedCard 조회 - 못 찾음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 조회 (없음)
        result = watcher.get_tracked_by_thread_ts("nonexistent_ts")
        assert result is None

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_build_reaction_execute_prompt(self, mock_config, mock_trello_client):
        """리액션 기반 실행 프롬프트 생성"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, ThreadCardInfo

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        info = ThreadCardInfo(
            thread_ts="1234567890.123456",
            channel_id="C12345",
            card_id="card123",
            card_name="기능 구현 작업",
            card_url="https://trello.com/c/abc123",
            created_at="2024-01-01T00:00:00"
        )

        prompt = watcher.build_reaction_execute_prompt(info)

        assert "🚀 리액션으로 실행이 요청된" in prompt
        assert "기능 구현 작업" in prompt
        assert "card123" in prompt
        assert "https://trello.com/c/abc123" in prompt
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt


class TestAutoMoveNoticeInPrompts:
    """프롬프트에 카드 자동 이동 안내가 포함되는지 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_to_go_execute_prompt_has_auto_move_notice(self, mock_config, mock_trello_client):
        """실행 모드 프롬프트에 자동 이동 안내 포함"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {}
        mock_config.trello.review_list_id = None
        mock_config.trello.done_list_id = None
        mock_config.trello.draft_list_id = None
        mock_config.trello.backlog_list_id = None
        mock_config.trello.blocked_list_id = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        card = TrelloCard(
            id="card123",
            name="테스트 태스크",
            desc="태스크 본문",
            url="https://trello.com/c/abc123",
            list_id="list123",
            labels=[],
        )

        prompt = watcher.prompt_builder.build_to_go(card, has_execute=True)
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt
        assert "In Progress로 이동하지 마세요" in prompt

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_to_go_plan_prompt_has_auto_move_notice(self, mock_config, mock_trello_client):
        """계획 모드 프롬프트에 자동 이동 안내 포함"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {}
        mock_config.trello.review_list_id = None
        mock_config.trello.done_list_id = None
        mock_config.trello.draft_list_id = None
        mock_config.trello.backlog_list_id = None
        mock_config.trello.blocked_list_id = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        card = TrelloCard(
            id="card456",
            name="계획 태스크",
            desc="태스크 본문",
            url="https://trello.com/c/def456",
            list_id="list123",
            labels=[],
        )

        prompt = watcher.prompt_builder.build_to_go(card, has_execute=False)
        assert "이미 워처에 의해 🔨 In Progress로 이동되었습니다" in prompt
        assert "In Progress로 이동하지 마세요" in prompt
        assert "📦 Backlog로 이동하세요" in prompt


class TestListRunSaySignature:
    """정주행 say() 함수가 send_long_message와 호환되는 시그니처를 갖는지 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_list_run_say_accepts_thread_ts_keyword(self, mock_config, mock_trello_client):
        """정주행 say()가 thread_ts= 키워드 인자를 받을 수 있어야 함

        send_long_message가 say(text=..., thread_ts=thread_ts)로 호출하므로,
        정주행용 say()도 thread_ts 키워드를 받아야 TypeError가 발생하지 않음.
        """
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {}
        mock_config.trello.review_list_id = None
        mock_config.trello.done_list_id = None
        mock_config.trello.in_progress_list_id = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        from seosoyoung.slackbot.trello.client import TrelloCard
        from seosoyoung.slackbot.slack.helpers import send_long_message

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )

            # 세션 생성
            session = list_runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            card = TrelloCard(
                id="card_a",
                name="Test Card",
                desc="",
                url="https://trello.com/c/abc",
                list_id="list_123",
                labels=[],
            )

            thread_ts = "1234567890.123456"

            # say를 PresentationContext에서 캡처하기 위해 claude_runner_factory를 이용
            captured_pctx = {}

            def capturing_factory(**kwargs):
                captured_pctx["presentation"] = kwargs.get("presentation")
                # 실행 완료 표시를 위해 mark_card_processed 호출
                list_runner.mark_card_processed(session.session_id, card.id, "completed")

            watcher.claude_runner_factory = capturing_factory

            # get_session_lock을 None으로 설정하여 lock 부분 스킵
            watcher.get_session_lock = None

            watcher._process_list_run_card(session.session_id, thread_ts)

            # PresentationContext에서 say 함수를 가져옴
            assert "presentation" in captured_pctx, "presentation이 claude_runner_factory에 전달되어야 함"
            say_fn = captured_pctx["presentation"].say

            # 핵심 테스트: send_long_message를 통해 호출했을 때 TypeError가 발생하지 않아야 함
            # send_long_message는 say(text=..., thread_ts=thread_ts)로 호출
            send_long_message(say_fn, "test message", "1234567890.999999")

            # 슬랙 메시지가 정상적으로 전송되었는지 확인
            calls = mock_slack.chat_postMessage.call_args_list
            # 마지막 호출이 send_long_message를 통한 것이어야 함
            last_call = calls[-1]
            assert last_call[1]["text"] == "test message"


class TestStaleTrackedCardCleanup:
    """방안 A: _poll() 시 만료된 _tracked 항목 자동 정리 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_stale_card_auto_untracked_after_timeout(self, mock_config, mock_trello_client):
        """2시간 이상 경과 + To Go에 없는 카드는 자동 untrack"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "list_togo"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_POLLING_DEBUG = False

        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []  # To Go 비어있음
        mock_trello.get_lists.return_value = []
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 3시간 전에 추적 시작된 카드 (만료 기준 초과)
        stale_time = (datetime.now() - timedelta(hours=3)).isoformat()
        tracked = TrackedCard(
            card_id="stale_card",
            card_name="Stuck Card",
            card_url="https://trello.com/c/stale",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="1111.2222",
            channel_id="C12345",
            detected_at=stale_time,
            session_id=None,  # 세션 없음
        )
        watcher._tracked["stale_card"] = tracked

        # 폴링 실행
        watcher._poll()

        # stale 카드가 untrack 되었어야 함
        assert "stale_card" not in watcher._tracked

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_recent_card_not_untracked(self, mock_config, mock_trello_client):
        """30분 전 추적 시작된 카드는 아직 만료되지 않아 유지"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "list_togo"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_POLLING_DEBUG = False

        mock_trello = MagicMock()
        mock_trello.get_cards_in_list.return_value = []
        mock_trello.get_lists.return_value = []
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 30분 전 추적 시작 (만료 기준 미달)
        recent_time = (datetime.now() - timedelta(minutes=30)).isoformat()
        tracked = TrackedCard(
            card_id="recent_card",
            card_name="Recent Card",
            card_url="https://trello.com/c/recent",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="3333.4444",
            channel_id="C12345",
            detected_at=recent_time,
        )
        watcher._tracked["recent_card"] = tracked

        watcher._poll()

        # 아직 유지되어야 함
        assert "recent_card" in watcher._tracked


class TestHandleNewCardFailureUntrack:
    """방안 B: _handle_new_card 실패 시 untrack 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_untrack_on_slack_message_failure(self, mock_config, mock_trello_client):
        """Slack 메시지 전송 실패 시 카드가 _tracked에 남지 않아야 함"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "list_inprogress"
        mock_config.TRELLO_DM_TARGET_USER_ID = None

        mock_trello = MagicMock()
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True
        mock_trello_client.return_value = mock_trello

        mock_slack = MagicMock()
        # DM 모드 비활성, notify_channel 메시지 전송 실패
        mock_slack.chat_postMessage.side_effect = Exception("Slack API error")

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        card = TrelloCard(
            id="fail_card",
            name="Fail Card",
            desc="",
            url="https://trello.com/c/fail",
            list_id="list_togo",
            labels=[],
        )

        watcher._handle_new_card(card, "to_go")

        # Slack 메시지 실패 시 _tracked에 카드가 남지 않아야 함
        assert "fail_card" not in watcher._tracked


class TestToGoReturnRetrack:
    """방안 C: 카드가 To Go로 다시 돌아왔을 때 re-track 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_card_returned_to_togo_is_retracked(self, mock_config, mock_trello_client):
        """이미 _tracked에 있는 카드가 다시 To Go에 나타나면 re-track"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "list_togo"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "list_inprogress"
        mock_config.TRELLO_DM_TARGET_USER_ID = None
        mock_config.TRELLO_POLLING_DEBUG = False

        mock_trello = MagicMock()
        mock_trello.move_card.return_value = True
        mock_trello.update_card_name.return_value = True
        mock_trello.get_lists.return_value = []
        mock_trello_client.return_value = mock_trello

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "9999.0000"}

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(create=MagicMock()),
            claude_runner_factory=MagicMock()
        )

        # stale tracked card (3시간 전)
        stale_time = (datetime.now() - timedelta(hours=3)).isoformat()
        old_tracked = TrackedCard(
            card_id="return_card",
            card_name="Return Card",
            card_url="https://trello.com/c/return",
            list_id="list_togo",
            list_key="to_go",
            thread_ts="old_thread",
            channel_id="C12345",
            detected_at=stale_time,
            session_id=None,
        )
        watcher._tracked["return_card"] = old_tracked

        # 이 카드가 다시 To Go에 있음
        card = TrelloCard(
            id="return_card",
            name="Return Card",
            desc="",
            url="https://trello.com/c/return",
            list_id="list_togo",
            labels=[],
        )
        mock_trello.get_cards_in_list.return_value = [card]

        watcher._poll()

        # stale 카드가 제거된 후 _handle_new_card로 다시 처리되어야 함
        # 또는 detected_at이 갱신되었어야 함
        # 핵심: 카드가 stuck 상태로 남지 않고 재처리됨
        assert "return_card" not in watcher._tracked or \
            watcher._tracked["return_card"].detected_at != stale_time


class TestPreemptiveCompact:
    """정주행 카드 완료 시 선제적 컨텍스트 컴팩트 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_compact_success_with_session_id(self, mock_config, mock_trello_client):
        """세션 ID가 있을 때 compact_session 호출 성공"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.claude.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session-abc123",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=mock_session_manager,
            claude_runner_factory=MagicMock(),
        )

        # ClaudeAgentRunner.compact_session을 mock
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "test-session-abc123"  # 동일 session_id

        with patch("seosoyoung.slackbot.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.compact_session.return_value = mock_result
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # compact_session이 올바른 session_id로 호출되었는지 확인
            mock_runner_instance.compact_session.assert_called_once_with("test-session-abc123")

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_compact_skipped_without_session_id(self, mock_config, mock_trello_client):
        """세션 ID가 없으면 compact를 스킵"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.claude.session import Session

        mock_session_manager = MagicMock()
        # session_id가 None인 세션
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id=None,
        )
        mock_session_manager.get.return_value = mock_session

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=mock_session_manager,
            claude_runner_factory=MagicMock(),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.ClaudeRunner") as MockRunner:
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # Runner가 생성되지 않아야 함
            MockRunner.assert_not_called()

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_compact_failure_does_not_block_next_card(self, mock_config, mock_trello_client):
        """compact 실패해도 예외가 전파되지 않아 다음 카드 처리를 막지 않음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.claude.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session-abc123",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=mock_session_manager,
            claude_runner_factory=MagicMock(),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            # compact_session이 예외를 발생시킴
            mock_runner_instance.run_sync.side_effect = RuntimeError("Connection failed")
            MockRunner.return_value = mock_runner_instance

            # 예외가 전파되지 않아야 함
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_compact_updates_session_id_when_changed(self, mock_config, mock_trello_client):
        """compact 후 세션 ID가 변경되면 session_manager에 업데이트"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.claude.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="old-session-id",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=mock_session_manager,
            claude_runner_factory=MagicMock(),
        )

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.session_id = "new-session-id"  # 변경된 session_id

        with patch("seosoyoung.slackbot.claude.agent_runner.ClaudeRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # session_manager.update_session_id가 새 ID로 호출되었는지 확인
            mock_session_manager.update_session_id.assert_called_once_with(
                "1234.5678", "new-session-id"
            )


class TestCheckRunListLabelsFiltering:
    """_check_run_list_labels 운영 리스트 필터링 및 가드 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_operational_lists_excluded(self, mock_config, mock_trello_client):
        """운영 리스트(In Progress, Review, Done 등)는 정주행 대상에서 제외"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {"to_go": "list_togo"}
        mock_config.trello.review_list_id = "list_review"
        mock_config.trello.done_list_id = "list_done"
        mock_config.trello.in_progress_list_id = "list_inprogress"
        mock_config.trello.backlog_list_id = "list_backlog"
        mock_config.trello.blocked_list_id = "list_blocked"
        mock_config.trello.draft_list_id = "list_draft"
        mock_config.trello.polling_debug = False

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        # 운영 리스트에 Run List 레이블이 있는 카드를 배치
        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card_in_progress = TrelloCard(
            id="card_ip", name="Card In Progress", desc="",
            url="", list_id="list_inprogress",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_inprogress", "name": "🔨 In Progress"},
            {"id": "list_review", "name": "👀 Review"},
            {"id": "list_togo", "name": "🚀 To Go"},
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card_in_progress]
        mock_trello.remove_label_from_card.return_value = True

        watcher._check_run_list_labels()

        # 운영 리스트가 아닌 list_plan만 카드 조회 대상이어야 함
        # get_cards_in_list는 list_plan에 대해서만 호출되어야 함
        call_args = [c[0][0] for c in mock_trello.get_cards_in_list.call_args_list]
        assert "list_inprogress" not in call_args
        assert "list_review" not in call_args
        assert "list_togo" not in call_args

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_label_removal_failure_skips_list_run(self, mock_config, mock_trello_client):
        """레이블 제거 실패 시 정주행을 시작하지 않아야 함"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = None
        mock_config.TRELLO_BACKLOG_LIST_ID = None
        mock_config.TRELLO_BLOCKED_LIST_ID = None
        mock_config.TRELLO_DRAFT_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
            list_runner_ref=MagicMock(return_value=MagicMock()),
        )

        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card = TrelloCard(
            id="card_plan", name="Plan Card", desc="",
            url="", list_id="list_plan",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card]
        # 레이블 제거 실패
        mock_trello.remove_label_from_card.return_value = False

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()
            # _start_list_run이 호출되지 않아야 함
            mock_start.assert_not_called()

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_active_session_guard_prevents_duplicate(self, mock_config, mock_trello_client):
        """동일 리스트에 활성 세션이 있으면 정주행 시작 안 함"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = None
        mock_config.TRELLO_BACKLOG_LIST_ID = None
        mock_config.TRELLO_BLOCKED_LIST_ID = None
        mock_config.TRELLO_DRAFT_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard

        # list_runner에 활성 세션이 있는 상태
        mock_list_runner = MagicMock()
        active_session = MagicMock()
        active_session.list_id = "list_plan"
        mock_list_runner.get_active_sessions.return_value = [active_session]

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
            list_runner_ref=lambda: mock_list_runner,
        )

        run_list_label = {"id": "label_run", "name": "🏃 Run List"}
        card = TrelloCard(
            id="card_plan", name="Plan Card", desc="",
            url="", list_id="list_plan",
            labels=[run_list_label],
        )

        mock_trello.get_lists.return_value = [
            {"id": "list_plan", "name": "📌 PLAN: Test"},
        ]
        mock_trello.get_cards_in_list.return_value = [card]
        mock_trello.remove_label_from_card.return_value = True

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()
            mock_start.assert_not_called()


class TestProcessListRunCardTracked:
    """_process_list_run_card가 _tracked에 등록하는지 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_list_run_card_registered_in_tracked(self, mock_config, mock_trello_client):
        """정주행 카드가 _tracked에 등록되어 To Go 감지와 중복 방지"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )

            # 세션 생성
            session = list_runner.create_session(
                list_id="list_123",
                list_name="Plan List",
                card_ids=["card_a"],
            )
            list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            card = TrelloCard(
                id="card_a", name="Test Card", desc="",
                url="https://trello.com/c/abc", list_id="list_123",
                labels=[],
            )
            mock_trello.get_card.return_value = card

            # _process_list_run_card 호출 전 _tracked 확인
            assert "card_a" not in watcher._tracked

            # 세션 락 없이 실행
            watcher.get_session_lock = None
            watcher._process_list_run_card(session.session_id, "1234567890.123456")

            # 정주행 카드가 _tracked에 등록되어야 함
            assert "card_a" in watcher._tracked
            assert watcher._tracked["card_a"].list_key == "list_run"

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_list_run_first_card_not_redetected_by_poll(self, mock_config, mock_trello_client):
        """정주행 첫 카드가 _tracked에 있으면 _poll에서 재감지되지 않음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_go": "list_togo"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = None
        mock_config.TRELLO_BACKLOG_LIST_ID = None
        mock_config.TRELLO_BLOCKED_LIST_ID = None
        mock_config.TRELLO_DRAFT_LIST_ID = None
        mock_config.TRELLO_POLLING_DEBUG = False

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello
        mock_trello.get_lists.return_value = []

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard
        from seosoyoung.slackbot.trello.client import TrelloCard

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        # 정주행으로 이미 _tracked에 등록된 카드
        tracked = TrackedCard(
            card_id="card_run_1",
            card_name="Run Card",
            card_url="https://trello.com/c/run1",
            list_id="list_plan",
            list_key="list_run",
            thread_ts="thread_123",
            channel_id="C12345",
            detected_at=datetime.now().isoformat(),
            has_execute=True,
        )
        watcher._tracked["card_run_1"] = tracked

        # 같은 카드가 To Go에도 나타남 (이론적으로 불가능하지만 방어적으로 테스트)
        card = TrelloCard(
            id="card_run_1", name="Run Card", desc="",
            url="https://trello.com/c/run1", list_id="list_togo",
            labels=[],
        )
        mock_trello.get_cards_in_list.return_value = [card]

        with patch.object(watcher, "_handle_new_card") as mock_handle:
            watcher._poll()
            # _tracked에 이미 있으므로 _handle_new_card가 호출되지 않아야 함
            mock_handle.assert_not_called()


class TestGetOperationalListIds:
    """_get_operational_list_ids 테스트"""

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_collects_all_operational_ids(self, mock_config, mock_trello_client):
        """모든 운영 리스트 ID가 수집됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {"to_go": "list_togo"}
        mock_config.trello.review_list_id = "list_review"
        mock_config.trello.done_list_id = "list_done"
        mock_config.trello.in_progress_list_id = "list_ip"
        mock_config.trello.backlog_list_id = "list_bl"
        mock_config.trello.blocked_list_id = "list_blocked"
        mock_config.trello.draft_list_id = "list_draft"

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        ids = watcher._get_operational_list_ids()
        assert "list_togo" in ids
        assert "list_review" in ids
        assert "list_done" in ids
        assert "list_ip" in ids
        assert "list_bl" in ids
        assert "list_blocked" in ids
        assert "list_draft" in ids

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_empty_ids_excluded(self, mock_config, mock_trello_client):
        """빈 문자열 ID는 제외됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.trello.notify_channel = "C12345"
        mock_config.trello.watch_lists = {"to_go": "list_togo"}
        mock_config.trello.review_list_id = ""
        mock_config.trello.done_list_id = None
        mock_config.trello.in_progress_list_id = "list_ip"
        mock_config.trello.backlog_list_id = ""
        mock_config.trello.blocked_list_id = None
        mock_config.trello.draft_list_id = ""

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        ids = watcher._get_operational_list_ids()
        assert "" not in ids
        assert None not in ids
        assert "list_togo" in ids
        assert "list_ip" in ids


class _SyncThread:
    """테스트용: threading.Thread를 동기적으로 실행하는 대체 클래스"""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **extra):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        if self.target:
            self.target(*self.args, **self.kwargs)


class TestMultiCardChainingIntegration:
    """멀티 카드 체이닝 통합 테스트 (card1→card2→card3→COMPLETED)

    _spawn_claude_thread가 별도 스레드를 생성하므로, claude_runner_factory를
    동기적으로 완료하도록 모킹하여 체이닝 흐름을 검증합니다.
    on_success 내부의 threading.Thread도 동기화하여 전체 체인을 검증합니다.
    """

    @patch("seosoyoung.slackbot.trello.watcher.threading.Thread", _SyncThread)
    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_three_card_chaining_completes(self, mock_config, mock_trello_client):
        """3장의 카드가 순차적으로 처리되고 세션이 COMPLETED 상태가 됨"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "list_inprogress"

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))
            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

            # _spawn_claude_thread를 오버라이드하여 동기적으로 on_success 호출
            def sync_spawn(*, session, prompt, thread_ts, channel,
                           tracked, dm_channel_id=None, dm_thread_ts=None,
                           on_success=None, on_error=None, on_finally=None):
                # Claude 실행 성공 시뮬레이션
                if on_success:
                    on_success()
                if on_finally:
                    on_finally()

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )
            watcher._spawn_claude_thread = sync_spawn

            # _preemptive_compact 모킹 (SDK 호출 불필요)
            watcher._preemptive_compact = MagicMock()

            # 카드 3장 설정
            cards_data = {
                "card_a": TrelloCard(
                    id="card_a", name="Card A", desc="",
                    url="https://trello.com/c/a", list_id="list_plan", labels=[],
                ),
                "card_b": TrelloCard(
                    id="card_b", name="Card B", desc="",
                    url="https://trello.com/c/b", list_id="list_plan", labels=[],
                ),
                "card_c": TrelloCard(
                    id="card_c", name="Card C", desc="",
                    url="https://trello.com/c/c", list_id="list_plan", labels=[],
                ),
            }
            mock_trello.get_card.side_effect = lambda cid: cards_data.get(cid)
            mock_trello.move_card.return_value = True
            mock_trello.update_card_name.return_value = True

            # 세션 생성
            session = list_runner.create_session(
                list_id="list_plan",
                list_name="Plan List",
                card_ids=["card_a", "card_b", "card_c"],
            )

            # 정주행 시작 (동기적으로 3장 전부 처리됨)
            watcher._process_list_run_card(session.session_id, "thread_123")

            # 검증: 세션 COMPLETED
            updated = list_runner.get_session(session.session_id)
            assert updated.status == SessionStatus.COMPLETED
            assert updated.current_index == 3
            assert updated.processed_cards == {
                "card_a": "completed",
                "card_b": "completed",
                "card_c": "completed",
            }

    @patch("seosoyoung.slackbot.trello.watcher.threading.Thread", _SyncThread)
    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_chaining_continues_after_compact_failure(self, mock_config, mock_trello_client):
        """_preemptive_compact 실패해도 체인이 끊기지 않음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "list_inprogress"

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))
            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

            def sync_spawn(*, session, prompt, thread_ts, channel,
                           tracked, dm_channel_id=None, dm_thread_ts=None,
                           on_success=None, on_error=None, on_finally=None):
                if on_success:
                    on_success()
                if on_finally:
                    on_finally()

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )
            watcher._spawn_claude_thread = sync_spawn

            # _preemptive_compact가 매번 예외를 던짐
            watcher._preemptive_compact = MagicMock(
                side_effect=RuntimeError("compact hang")
            )

            cards_data = {
                "card_a": TrelloCard(
                    id="card_a", name="Card A", desc="",
                    url="https://trello.com/c/a", list_id="list_plan", labels=[],
                ),
                "card_b": TrelloCard(
                    id="card_b", name="Card B", desc="",
                    url="https://trello.com/c/b", list_id="list_plan", labels=[],
                ),
            }
            mock_trello.get_card.side_effect = lambda cid: cards_data.get(cid)
            mock_trello.move_card.return_value = True
            mock_trello.update_card_name.return_value = True

            session = list_runner.create_session(
                list_id="list_plan",
                list_name="Plan List",
                card_ids=["card_a", "card_b"],
            )

            watcher._process_list_run_card(session.session_id, "thread_123")

            # compact 실패에도 2장 모두 처리 완료
            updated = list_runner.get_session(session.session_id)
            assert updated.status == SessionStatus.COMPLETED
            assert updated.current_index == 2

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_on_success_exception_does_not_trigger_on_error(self, mock_config, mock_trello_client):
        """on_success 예외가 on_error를 트리거하지 않음 (_spawn_claude_thread 격리 검증)"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher, TrackedCard

        mock_slack = MagicMock()
        mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

        watcher = TrelloWatcher(
            slack_client=mock_slack,
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),  # 성공 (예외 없음)
        )

        tracked = TrackedCard(
            card_id="card_test",
            card_name="Test Card",
            card_url="",
            list_id="list_test",
            list_key="test",
            thread_ts="thread_123",
            channel_id="C12345",
            detected_at="2026-01-01T00:00:00",
        )

        on_error_called = []

        def failing_on_success():
            raise RuntimeError("on_success exploded")

        def tracking_on_error(e):
            on_error_called.append(e)

        # _spawn_claude_thread 직접 호출 후 스레드 완료 대기
        watcher.get_session_lock = None
        watcher._spawn_claude_thread(
            session=MagicMock(),
            prompt="test",
            thread_ts="thread_123",
            channel="C12345",
            tracked=tracked,
            on_success=failing_on_success,
            on_error=tracking_on_error,
        )

        # 스레드 완료 대기
        import time
        time.sleep(0.5)

        # on_error가 호출되지 않아야 함 (Claude 실행 자체는 성공)
        assert len(on_error_called) == 0

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_process_list_run_card_handles_trello_api_error(self, mock_config, mock_trello_client):
        """_process_list_run_card에서 Trello API 오류 시 전역 try-except가 잡음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = "list_ip"

        mock_trello = MagicMock()
        # get_card가 예외를 던짐
        mock_trello.get_card.side_effect = ConnectionError("Trello API down")
        mock_trello_client.return_value = mock_trello

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))
            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "thread_123"}

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )

            session = list_runner.create_session(
                list_id="list_plan",
                list_name="Plan",
                card_ids=["card_a"],
            )
            list_runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            # 예외가 전파되지 않아야 함 (전역 try-except)
            watcher._process_list_run_card(session.session_id, "thread_123")

            # 세션이 PAUSED로 변경되어야 함
            updated = list_runner.get_session(session.session_id)
            assert updated.status == SessionStatus.PAUSED

    @patch("seosoyoung.slackbot.trello.watcher.TrelloClient")
    @patch("seosoyoung.slackbot.trello.watcher.Config")
    def test_compact_timeout_does_not_block_chain(self, mock_config, mock_trello_client):
        """_preemptive_compact 타임아웃 시 체인이 계속됨"""
        import concurrent.futures

        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.claude.session import Session

        mock_session_manager = MagicMock()
        mock_session = Session(
            thread_ts="1234.5678",
            channel_id="C12345",
            session_id="test-session",
        )
        mock_session_manager.get.return_value = mock_session

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=mock_session_manager,
            claude_runner_factory=MagicMock(),
        )

        # future.result()가 TimeoutError를 raise하도록 mock 설정
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError()

        mock_pool = MagicMock()
        mock_pool.__enter__ = MagicMock(return_value=mock_pool)
        mock_pool.__exit__ = MagicMock(return_value=False)
        mock_pool.submit.return_value = mock_future

        with patch("seosoyoung.slackbot.claude.agent_runner.ClaudeRunner") as MockRunner, \
             patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_pool):
            MockRunner.return_value = MagicMock()

            # TimeoutError가 발생해도 정상 반환 (예외 전파 없음)
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # submit이 호출되었는지 확인
            mock_pool.submit.assert_called_once()
            # future.result()에 timeout이 전달되었는지 확인
            mock_future.result.assert_called_once_with(
                timeout=watcher.COMPACT_TIMEOUT_SECONDS
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
