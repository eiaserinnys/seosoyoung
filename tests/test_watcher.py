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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
