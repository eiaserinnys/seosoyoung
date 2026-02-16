"""TrelloWatcher 테스트"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import threading


class TestTrelloWatcherPauseResume:
    """TrelloWatcher pause/resume 기능 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_initial_not_paused(self, mock_config, mock_trello_client):
        """초기 상태는 일시 중단 아님"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        assert watcher.is_paused is False

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_pause(self, mock_config, mock_trello_client):
        """일시 중단"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        watcher.pause()

        assert watcher.is_paused is True

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_resume(self, mock_config, mock_trello_client):
        """재개"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        watcher.pause()
        assert watcher.is_paused is True

        watcher.resume()
        assert watcher.is_paused is False

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_poll_skipped_when_paused(self, mock_config, mock_trello_client):
        """일시 중단 상태면 폴링 스킵"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {"to_plan": "list123"}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        mock_trello = MagicMock()
        mock_trello_client.return_value = mock_trello

        from seosoyoung.trello.watcher import TrelloWatcher

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
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

        from seosoyoung.trello.watcher import TrelloWatcher

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_get_tracked_by_thread_ts_found(self, mock_config, mock_trello_client):
        """thread_ts로 TrackedCard 조회 - 찾음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_get_tracked_by_thread_ts_not_found(self, mock_config, mock_trello_client):
        """thread_ts로 TrackedCard 조회 - 못 찾음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock()
        )

        # 조회 (없음)
        result = watcher.get_tracked_by_thread_ts("nonexistent_ts")
        assert result is None

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_build_reaction_execute_prompt(self, mock_config, mock_trello_client):
        """리액션 기반 실행 프롬프트 생성"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher, ThreadCardInfo

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


class TestListRunSaySignature:
    """정주행 say() 함수가 send_long_message와 호환되는 시그니처를 갖는지 테스트"""

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_list_run_say_accepts_thread_ts_keyword(self, mock_config, mock_trello_client):
        """정주행 say()가 thread_ts= 키워드 인자를 받을 수 있어야 함

        send_long_message가 say(text=..., thread_ts=thread_ts)로 호출하므로,
        정주행용 say()도 thread_ts 키워드를 받아야 TypeError가 발생하지 않음.
        """
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None
        mock_config.TRELLO_IN_PROGRESS_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus
        from seosoyoung.trello.client import TrelloCard
        from seosoyoung.slack.helpers import send_long_message

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

            # _process_list_run_card 내부에서 생성되는 say 함수를 시뮬레이션
            # watcher._process_list_run_card를 직접 호출하지 않고,
            # 해당 메서드 내의 say 함수 패턴을 재현하여 테스트
            thread_ts = "1234567890.123456"

            # say 함수를 캡처하기 위해 claude_runner_factory를 이용
            captured_say = {}

            def capturing_factory(**kwargs):
                captured_say["say"] = kwargs.get("say")
                # 실행 완료 표시를 위해 mark_card_processed 호출
                list_runner.mark_card_processed(session.session_id, card.id, "completed")

            watcher.claude_runner_factory = capturing_factory

            # _process_list_run_card 호출 (별도 스레드 방지를 위해 직접 호출)
            # get_session_lock을 None으로 설정하여 lock 부분 스킵
            watcher.get_session_lock = None

            watcher._process_list_run_card(session.session_id, thread_ts)

            # say 함수가 캡처되었는지 확인
            assert "say" in captured_say, "say 함수가 claude_runner_factory에 전달되어야 함"
            say_fn = captured_say["say"]

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
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

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
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

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
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

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.trello.client import TrelloCard

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
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

        from seosoyoung.trello.watcher import TrelloWatcher, TrackedCard
        from seosoyoung.trello.client import TrelloCard

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

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_compact_success_with_session_id(self, mock_config, mock_trello_client):
        """세션 ID가 있을 때 compact_session 호출 성공"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.claude.session import Session

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

        with patch("seosoyoung.claude.agent_runner.ClaudeAgentRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.compact_session.return_value = mock_result
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # compact_session이 올바른 session_id로 호출되었는지 확인
            mock_runner_instance.compact_session.assert_called_once_with("test-session-abc123")

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_compact_skipped_without_session_id(self, mock_config, mock_trello_client):
        """세션 ID가 없으면 compact를 스킵"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.claude.session import Session

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

        with patch("seosoyoung.claude.agent_runner.ClaudeAgentRunner") as MockRunner:
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # Runner가 생성되지 않아야 함
            MockRunner.assert_not_called()

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_compact_failure_does_not_block_next_card(self, mock_config, mock_trello_client):
        """compact 실패해도 예외가 전파되지 않아 다음 카드 처리를 막지 않음"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.claude.session import Session

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

        with patch("seosoyoung.claude.agent_runner.ClaudeAgentRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            # compact_session이 예외를 발생시킴
            mock_runner_instance.run_sync.side_effect = RuntimeError("Connection failed")
            MockRunner.return_value = mock_runner_instance

            # 예외가 전파되지 않아야 함
            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

    @patch("seosoyoung.trello.watcher.TrelloClient")
    @patch("seosoyoung.trello.watcher.Config")
    def test_compact_updates_session_id_when_changed(self, mock_config, mock_trello_client):
        """compact 후 세션 ID가 변경되면 session_manager에 업데이트"""
        mock_config.get_session_path.return_value = "/tmp/sessions"
        mock_config.TRELLO_NOTIFY_CHANNEL = "C12345"
        mock_config.TRELLO_WATCH_LISTS = {}
        mock_config.TRELLO_REVIEW_LIST_ID = None
        mock_config.TRELLO_DONE_LIST_ID = None

        from seosoyoung.trello.watcher import TrelloWatcher
        from seosoyoung.claude.session import Session

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

        with patch("seosoyoung.claude.agent_runner.ClaudeAgentRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            watcher._preemptive_compact("1234.5678", "C12345", "Test Card")

            # session_manager.update_session_id가 새 ID로 호출되었는지 확인
            mock_session_manager.update_session_id.assert_called_once_with(
                "1234.5678", "new-session-id"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
