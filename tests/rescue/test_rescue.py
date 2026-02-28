"""rescue-bot 테스트

rescue-bot 고유 로직(config, main 핸들러)을 테스트합니다.
ClaudeRunner 내부 동작(SDK 통신, 에러 분류, rate_limit 처리, 클라이언트 생명주기 등)은
tests/claude/test_agent_runner.py에서 검증하므로 여기서는 제외합니다.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.rescue.claude.engine_types import EngineResult


class TestRescueConfig:
    """RescueConfig 테스트"""

    def test_validate_missing_bot_token(self):
        """RESCUE_SLACK_BOT_TOKEN이 없으면 예외 발생"""
        with patch.dict(os.environ, {}, clear=False):
            from seosoyoung.rescue.config import RescueConfig

            original_bot = RescueConfig.SLACK_BOT_TOKEN
            original_app = RescueConfig.SLACK_APP_TOKEN
            try:
                RescueConfig.SLACK_BOT_TOKEN = ""
                RescueConfig.SLACK_APP_TOKEN = "xapp-test"
                with pytest.raises(RuntimeError, match="RESCUE_SLACK_BOT_TOKEN"):
                    RescueConfig.validate()
            finally:
                RescueConfig.SLACK_BOT_TOKEN = original_bot
                RescueConfig.SLACK_APP_TOKEN = original_app

    def test_validate_missing_app_token(self):
        """RESCUE_SLACK_APP_TOKEN이 없으면 예외 발생"""
        from seosoyoung.rescue.config import RescueConfig

        original_bot = RescueConfig.SLACK_BOT_TOKEN
        original_app = RescueConfig.SLACK_APP_TOKEN
        try:
            RescueConfig.SLACK_BOT_TOKEN = "xoxb-test"
            RescueConfig.SLACK_APP_TOKEN = ""
            with pytest.raises(RuntimeError, match="RESCUE_SLACK_APP_TOKEN"):
                RescueConfig.validate()
        finally:
            RescueConfig.SLACK_BOT_TOKEN = original_bot
            RescueConfig.SLACK_APP_TOKEN = original_app

    def test_validate_success(self):
        """토큰이 모두 있으면 예외 없음"""
        from seosoyoung.rescue.config import RescueConfig

        original_bot = RescueConfig.SLACK_BOT_TOKEN
        original_app = RescueConfig.SLACK_APP_TOKEN
        try:
            RescueConfig.SLACK_BOT_TOKEN = "xoxb-test"
            RescueConfig.SLACK_APP_TOKEN = "xapp-test"
            RescueConfig.validate()  # 예외 없어야 함
        finally:
            RescueConfig.SLACK_BOT_TOKEN = original_bot
            RescueConfig.SLACK_APP_TOKEN = original_app

    def test_get_working_dir(self):
        """작업 디렉토리는 cwd를 반환"""
        from pathlib import Path

        from seosoyoung.rescue.config import RescueConfig

        assert RescueConfig.get_working_dir() == Path.cwd()


class TestRescueMain:
    """main.py 핸들러 테스트 (RescueBotApp 클래스 기반)"""

    @pytest.fixture
    def app(self):
        """RescueBotApp 인스턴스를 생성하고 bot_user_id를 설정"""
        from seosoyoung.rescue.main import RescueBotApp

        bot_app = RescueBotApp()
        bot_app.bot_user_id = "U_RESCUE"
        return bot_app

    def test_strip_mention(self, app):
        """멘션 태그 제거"""
        assert app._strip_mention("<@U_RESCUE> 안녕") == "안녕"
        assert app._strip_mention("<@U_RESCUE> <@U99999> 테스트") == "테스트"
        assert app._strip_mention("멘션 없음") == "멘션 없음"
        assert app._strip_mention("<@U_RESCUE>") == ""

    def test_strip_mention_no_bot_id(self):
        """봇 ID가 None일 때도 동작"""
        from seosoyoung.rescue.main import RescueBotApp

        bot_app = RescueBotApp()
        bot_app.bot_user_id = None
        # bot_user_id가 None이면 <@xxx> 패턴을 일괄 제거
        result = bot_app._strip_mention("<@U12345> 테스트")
        assert result == "테스트"

    def test_contains_bot_mention(self, app):
        """봇 멘션 감지"""
        assert app._contains_bot_mention("<@U_RESCUE> 안녕") is True
        assert app._contains_bot_mention("안녕하세요") is False
        assert app._contains_bot_mention("<@UOTHER> 안녕") is False

    def test_session_management(self, app):
        """세션 저장/조회 (SessionManager 기반)"""
        assert app._get_session("thread_999") is None
        session = app._get_or_create_session("thread_999", "C123")
        assert session is not None
        assert app._get_session("thread_999") is not None

    def test_handle_mention_empty_prompt(self, app):
        """빈 프롬프트일 때 안내 메시지"""
        event = {
            "channel": "C123",
            "user": "U456",
            "text": "<@U_RESCUE>",
            "ts": "1234.5678",
        }
        say = MagicMock()
        client = MagicMock()

        app.handle_mention(event, say, client)
        say.assert_called_once()
        assert "말씀해 주세요" in say.call_args[1]["text"]

    def test_handle_mention_success_saves_session(self, app):
        """정상 멘션 처리 후 session이 생성되는지 확인"""
        event = {
            "channel": "C123",
            "user": "U456",
            "text": "<@U_RESCUE> 안녕",
            "ts": "5555.6666",
        }
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "9999.0000"}

        mock_result = EngineResult(
            success=True, output="안녕하세요!", session_id="new-session-id"
        )

        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = mock_result

        with patch("seosoyoung.rescue.main.create_runner", return_value=mock_runner):
            app.handle_mention(event, say, client)

        # 세션이 생성되었는지 확인
        session = app._get_session("5555.6666")
        assert session is not None

    def test_handle_message_no_session(self, app):
        """세션이 없는 스레드 메시지는 무시"""
        event = {
            "channel": "C123",
            "user": "U456",
            "text": "후속 질문",
            "ts": "2000.0001",
            "thread_ts": "nonexistent_thread",
        }
        say = MagicMock()
        client = MagicMock()

        app.handle_message(event, say, client)
        say.assert_not_called()
        client.chat_postMessage.assert_not_called()

    def test_handle_message_with_session(self, app):
        """세션이 있는 스레드 메시지는 처리"""
        # 먼저 세션을 생성
        session = app._get_or_create_session("thread_100", "C123")
        app.sessions.update_session_id("thread_100", "existing-session")

        event = {
            "channel": "C123",
            "user": "U456",
            "text": "후속 질문입니다",
            "ts": "2000.0001",
            "thread_ts": "thread_100",
        }
        say = MagicMock()
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "9999.0000"}

        mock_result = EngineResult(
            success=True, output="후속 답변", session_id="existing-session"
        )

        mock_runner = MagicMock()
        mock_runner.run_sync.return_value = mock_result

        with patch("seosoyoung.rescue.main.create_runner", return_value=mock_runner):
            app.handle_message(event, say, client)

        client.chat_postMessage.assert_called_once()

    def test_handle_message_ignores_bot_mention(self, app):
        """봇 멘션이 포함된 스레드 메시지는 handle_mention에서 처리하므로 무시"""
        # 세션 생성
        app._get_or_create_session("thread_200", "C123")
        app.sessions.update_session_id("thread_200", "some-session")

        event = {
            "channel": "C123",
            "user": "U456",
            "text": "<@U_RESCUE> 멘션 포함 메시지",
            "ts": "2000.0002",
            "thread_ts": "thread_200",
        }
        say = MagicMock()
        client = MagicMock()

        app.handle_message(event, say, client)
        say.assert_not_called()
        client.chat_postMessage.assert_not_called()

    def test_handle_message_ignores_channel_message(self, app):
        """스레드가 아닌 채널 메시지는 무시"""
        event = {
            "channel": "C123",
            "user": "U456",
            "text": "채널에 직접 보낸 메시지",
            "ts": "2000.0003",
        }
        say = MagicMock()
        client = MagicMock()

        app.handle_message(event, say, client)
        say.assert_not_called()

    def test_handle_message_ignores_bot_message(self, app):
        """봇 자신의 메시지는 무시"""
        app._get_or_create_session("thread_300", "C123")
        app.sessions.update_session_id("thread_300", "some-session")

        event = {
            "channel": "C123",
            "bot_id": "B123",
            "text": "봇의 메시지",
            "ts": "2000.0004",
            "thread_ts": "thread_300",
        }
        say = MagicMock()
        client = MagicMock()

        app.handle_message(event, say, client)
        say.assert_not_called()
