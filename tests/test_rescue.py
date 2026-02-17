"""rescue-bot 테스트"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRescueConfig:
    """RescueConfig 테스트"""

    def test_validate_missing_bot_token(self):
        """RESCUE_SLACK_BOT_TOKEN이 없으면 예외 발생"""
        with patch.dict(os.environ, {}, clear=False):
            from seosoyoung.rescue.config import RescueConfig

            # 토큰을 빈 값으로 설정
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


class TestRescueRunner:
    """runner.run_claude 테스트"""

    def test_run_claude_success(self):
        """정상 실행 시 성공 결과 반환"""
        from seosoyoung.rescue.runner import RescueResult

        mock_result_msg = MagicMock()
        mock_result_msg.result = "테스트 응답"
        type(mock_result_msg).__name__ = "ResultMessage"

        async def mock_query(**kwargs):
            # ResultMessage만 yield
            from claude_code_sdk.types import ResultMessage

            msg = MagicMock(spec=ResultMessage)
            msg.result = "테스트 응답"
            msg.is_error = False
            yield msg

        with patch("seosoyoung.rescue.runner.query", side_effect=mock_query):
            from seosoyoung.rescue.runner import run_claude

            result = asyncio.run(run_claude("테스트 프롬프트"))
            assert result.success is True
            assert result.output == "테스트 응답"
            assert result.error is None

    def test_run_claude_process_error(self):
        """ProcessError 발생 시 실패 결과 반환"""
        from claude_code_sdk._errors import ProcessError

        async def mock_query(**kwargs):
            raise ProcessError(message="test error", exit_code=1, stderr="test error")
            yield  # make it a generator  # noqa: E275

        with patch("seosoyoung.rescue.runner.query", side_effect=mock_query):
            from seosoyoung.rescue.runner import run_claude

            result = asyncio.run(run_claude("테스트"))
            assert result.success is False
            assert "exit code: 1" in result.error

    def test_run_claude_generic_exception(self):
        """일반 예외 발생 시 실패 결과 반환"""

        async def mock_query(**kwargs):
            raise RuntimeError("unexpected")
            yield  # noqa: E275

        with patch("seosoyoung.rescue.runner.query", side_effect=mock_query):
            from seosoyoung.rescue.runner import run_claude

            result = asyncio.run(run_claude("테스트"))
            assert result.success is False
            assert "unexpected" in result.error


class TestRescueMain:
    """main.py 핸들러 테스트"""

    def test_strip_mention(self):
        """멘션 태그 제거"""
        from seosoyoung.rescue.main import _strip_mention

        assert _strip_mention("<@U12345> 안녕", "U12345") == "안녕"
        assert _strip_mention("<@U12345> <@U99999> 테스트", "U12345") == "테스트"
        assert _strip_mention("멘션 없음", "U12345") == "멘션 없음"
        assert _strip_mention("<@U12345>", "U12345") == ""

    def test_strip_mention_no_bot_id(self):
        """봇 ID가 None일 때도 동작"""
        from seosoyoung.rescue.main import _strip_mention

        assert _strip_mention("<@U12345> 테스트", None) == "테스트"

    def test_handle_mention_empty_prompt(self):
        """빈 프롬프트일 때 안내 메시지"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import handle_mention

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"

            event = {
                "channel": "C123",
                "user": "U456",
                "text": "<@U_RESCUE>",
                "ts": "1234.5678",
            }
            say = MagicMock()
            client = MagicMock()

            handle_mention(event, say, client)
            say.assert_called_once()
            assert "말씀해 주세요" in say.call_args[1]["text"]
        finally:
            RescueConfig.BOT_USER_ID = original_id

    def test_handle_mention_success(self):
        """정상 멘션 처리"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import handle_mention
        from seosoyoung.rescue.runner import RescueResult

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"

            event = {
                "channel": "C123",
                "user": "U456",
                "text": "<@U_RESCUE> 안녕",
                "ts": "1234.5678",
            }
            say = MagicMock()
            client = MagicMock()
            client.chat_postMessage.return_value = {"ts": "9999.0000"}

            mock_result = RescueResult(success=True, output="안녕하세요!")

            with patch(
                "seosoyoung.rescue.main.run_claude",
                return_value=mock_result,
            ) as mock_run:
                with patch("seosoyoung.rescue.main.asyncio") as mock_asyncio:
                    mock_asyncio.run.return_value = mock_result
                    handle_mention(event, say, client)

            # 사고 과정 메시지가 전송되어야 함
            client.chat_postMessage.assert_called_once()
            # 결과로 업데이트되어야 함
            client.chat_update.assert_called_once()
            update_call = client.chat_update.call_args
            assert update_call[1]["text"] == "안녕하세요!"
        finally:
            RescueConfig.BOT_USER_ID = original_id
