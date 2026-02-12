"""TrelloWatcher 테스트"""

import pytest
from unittest.mock import MagicMock, patch
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
