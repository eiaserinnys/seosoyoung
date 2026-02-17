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
    """runner.run_claude 테스트 (ClaudeSDKClient 기반)"""

    def test_run_claude_success(self):
        """정상 실행 시 성공 결과 반환 + session_id 포함"""
        from claude_code_sdk.types import ResultMessage, SystemMessage

        mock_system = MagicMock(spec=SystemMessage)
        mock_system.session_id = "test-session-123"

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "테스트 응답"
        mock_result.session_id = "test-session-123"
        mock_result.is_error = False

        async def mock_receive():
            yield mock_system
            yield mock_result

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            from seosoyoung.rescue.runner import _run_claude

            result = asyncio.run(_run_claude("테스트 프롬프트"))
            assert result.success is True
            assert result.output == "테스트 응답"
            assert result.session_id == "test-session-123"
            assert result.error is None

    def test_run_claude_with_resume(self):
        """세션 재개 시 resume 옵션 전달 확인"""
        from claude_code_sdk.types import ResultMessage, SystemMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "이어진 응답"
        mock_result.session_id = "test-session-123"

        async def mock_receive():
            yield mock_result

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.disconnect = AsyncMock()

        captured_options = {}

        def capture_client(options=None):
            captured_options["options"] = options
            return mock_client

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", side_effect=capture_client):
            from seosoyoung.rescue.runner import _run_claude

            result = asyncio.run(_run_claude("후속 질문", session_id="test-session-123"))
            assert result.success is True
            assert result.output == "이어진 응답"
            # resume 옵션이 전달되었는지 확인
            assert captured_options["options"].resume == "test-session-123"

    def test_run_claude_process_error(self):
        """ProcessError 발생 시 실패 결과 반환"""
        from claude_code_sdk._errors import ProcessError

        mock_client = MagicMock()
        mock_client.connect = AsyncMock(
            side_effect=ProcessError(message="test error", exit_code=1, stderr="test error")
        )
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            from seosoyoung.rescue.runner import _run_claude

            result = asyncio.run(_run_claude("테스트"))
            assert result.success is False
            assert "exit code: 1" in result.error

    def test_run_claude_generic_exception(self):
        """일반 예외 발생 시 실패 결과 반환"""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=RuntimeError("unexpected"))
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            from seosoyoung.rescue.runner import _run_claude

            result = asyncio.run(_run_claude("테스트"))
            assert result.success is False
            assert "unexpected" in result.error

    def test_run_claude_disconnect_on_success(self):
        """성공 후 disconnect가 호출되는지 확인"""
        from claude_code_sdk.types import ResultMessage

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.result = "응답"
        mock_result.session_id = None

        async def mock_receive():
            yield mock_result

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            from seosoyoung.rescue.runner import _run_claude

            asyncio.run(_run_claude("테스트"))
            mock_client.disconnect.assert_awaited_once()


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

    def test_contains_bot_mention(self):
        """봇 멘션 감지"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import _contains_bot_mention

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"
            assert _contains_bot_mention("<@U_RESCUE> 안녕") is True
            assert _contains_bot_mention("안녕하세요") is False
            assert _contains_bot_mention("<@UOTHER> 안녕") is False
        finally:
            RescueConfig.BOT_USER_ID = original_id

    def test_session_management(self):
        """세션 ID 저장/조회"""
        from seosoyoung.rescue.main import _get_session_id, _set_session_id

        assert _get_session_id("thread_999") is None
        _set_session_id("thread_999", "session-abc")
        assert _get_session_id("thread_999") == "session-abc"

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

    def test_handle_mention_success_saves_session(self):
        """정상 멘션 처리 후 session_id가 저장되는지 확인"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import (
            _get_session_id,
            handle_mention,
        )
        from seosoyoung.rescue.runner import RescueResult

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"

            event = {
                "channel": "C123",
                "user": "U456",
                "text": "<@U_RESCUE> 안녕",
                "ts": "5555.6666",
            }
            say = MagicMock()
            client = MagicMock()
            client.chat_postMessage.return_value = {"ts": "9999.0000"}

            mock_result = RescueResult(
                success=True, output="안녕하세요!", session_id="new-session-id"
            )

            with patch(
                "seosoyoung.rescue.main.run_claude_sync",
                return_value=mock_result,
            ):
                handle_mention(event, say, client)

            # 세션 ID가 저장되어야 함
            assert _get_session_id("5555.6666") == "new-session-id"
            # 결과로 업데이트되어야 함
            client.chat_update.assert_called_once()
            update_call = client.chat_update.call_args
            assert update_call[1]["text"] == "안녕하세요!"
        finally:
            RescueConfig.BOT_USER_ID = original_id

    def test_handle_message_no_session(self):
        """세션이 없는 스레드 메시지는 무시"""
        from seosoyoung.rescue.main import handle_message

        event = {
            "channel": "C123",
            "user": "U456",
            "text": "후속 질문",
            "ts": "2000.0001",
            "thread_ts": "nonexistent_thread",
        }
        say = MagicMock()
        client = MagicMock()

        handle_message(event, say, client)
        # 세션이 없으므로 아무 반응 없어야 함
        say.assert_not_called()
        client.chat_postMessage.assert_not_called()

    def test_handle_message_with_session(self):
        """세션이 있는 스레드 메시지는 처리"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import (
            _set_session_id,
            handle_message,
        )
        from seosoyoung.rescue.runner import RescueResult

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"

            # 세션 미리 설정
            _set_session_id("thread_100", "existing-session")

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

            mock_result = RescueResult(
                success=True, output="후속 답변", session_id="existing-session"
            )

            with patch(
                "seosoyoung.rescue.main.run_claude_sync",
                return_value=mock_result,
            ):
                handle_message(event, say, client)

            # 처리되어야 함
            client.chat_postMessage.assert_called_once()
            client.chat_update.assert_called_once()
        finally:
            RescueConfig.BOT_USER_ID = original_id

    def test_handle_message_ignores_bot_mention(self):
        """봇 멘션이 포함된 스레드 메시지는 handle_mention에서 처리하므로 무시"""
        from seosoyoung.rescue.config import RescueConfig
        from seosoyoung.rescue.main import (
            _set_session_id,
            handle_message,
        )

        original_id = RescueConfig.BOT_USER_ID
        try:
            RescueConfig.BOT_USER_ID = "U_RESCUE"

            _set_session_id("thread_200", "some-session")

            event = {
                "channel": "C123",
                "user": "U456",
                "text": "<@U_RESCUE> 멘션 포함 메시지",
                "ts": "2000.0002",
                "thread_ts": "thread_200",
            }
            say = MagicMock()
            client = MagicMock()

            handle_message(event, say, client)
            # 멘션 포함이므로 무시 (handle_mention에서 처리)
            say.assert_not_called()
            client.chat_postMessage.assert_not_called()
        finally:
            RescueConfig.BOT_USER_ID = original_id

    def test_handle_message_ignores_channel_message(self):
        """스레드가 아닌 채널 메시지는 무시"""
        from seosoyoung.rescue.main import handle_message

        event = {
            "channel": "C123",
            "user": "U456",
            "text": "채널에 직접 보낸 메시지",
            "ts": "2000.0003",
            # thread_ts가 없음
        }
        say = MagicMock()
        client = MagicMock()

        handle_message(event, say, client)
        say.assert_not_called()

    def test_handle_message_ignores_bot_message(self):
        """봇 자신의 메시지는 무시"""
        from seosoyoung.rescue.main import _set_session_id, handle_message

        _set_session_id("thread_300", "some-session")

        event = {
            "channel": "C123",
            "bot_id": "B123",
            "text": "봇의 메시지",
            "ts": "2000.0004",
            "thread_ts": "thread_300",
        }
        say = MagicMock()
        client = MagicMock()

        handle_message(event, say, client)
        say.assert_not_called()
