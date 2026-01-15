"""Main 모듈 테스트"""

import pytest
from unittest.mock import MagicMock, patch

# conftest.py에서 환경 변수가 설정되므로 import 가능
from seosoyoung.main import extract_command, send_long_message, check_permission


class TestExtractCommand:
    """extract_command 함수 테스트"""

    def test_extract_command_basic(self):
        """기본 명령어 추출"""
        result = extract_command("<@U12345> help")
        assert result == "help"

    def test_extract_command_uppercase(self):
        """대문자 명령어는 소문자로 변환"""
        result = extract_command("<@U12345> HELP")
        assert result == "help"

    def test_extract_command_with_extra_spaces(self):
        """공백이 있는 명령어"""
        result = extract_command("<@U12345>   cc  ")
        assert result == "cc"

    def test_extract_command_empty(self):
        """빈 명령어"""
        result = extract_command("<@U12345>")
        assert result == ""

    def test_extract_command_multiple_mentions(self):
        """여러 멘션이 있는 경우"""
        result = extract_command("<@U12345> <@U67890> status")
        assert result == "status"


class TestSendLongMessage:
    """send_long_message 함수 테스트"""

    def test_send_short_message(self):
        """짧은 메시지는 한 번에 전송"""
        mock_say = MagicMock()
        send_long_message(mock_say, "Hello", "thread-123")

        mock_say.assert_called_once()
        args = mock_say.call_args
        assert "Hello" in args.kwargs["text"]
        assert args.kwargs["thread_ts"] == "thread-123"

    def test_send_long_message_split(self):
        """긴 메시지는 분할 전송 (줄 단위로 분할됨)"""
        mock_say = MagicMock()
        # 줄바꿈 기준으로 분할하므로 여러 줄 생성
        long_text = "\n".join(["A" * 500] * 20)  # 500*20 + 19 줄바꿈 = 약 10000자
        send_long_message(mock_say, long_text, "thread-123")

        # 여러 번 호출되어야 함
        assert mock_say.call_count >= 2

    def test_send_message_with_newlines(self):
        """줄바꿈이 있는 긴 메시지"""
        mock_say = MagicMock()
        # 줄바꿈으로 구분된 긴 텍스트
        lines = ["Line " + str(i) + " " * 100 for i in range(100)]
        long_text = "\n".join(lines)
        send_long_message(mock_say, long_text, "thread-123")

        # 여러 번 호출되어야 함
        assert mock_say.call_count >= 2
        # 첫 번째 호출에 (1/N) 형태가 포함되어야 함
        first_call = mock_say.call_args_list[0]
        assert "(1/" in first_call.kwargs["text"]


class TestCheckPermission:
    """check_permission 함수 테스트"""

    @patch("seosoyoung.main.Config")
    def test_check_permission_allowed_user(self, mock_config):
        """허용된 사용자"""
        mock_config.ALLOWED_USERS = ["testuser"]

        mock_client = MagicMock()
        mock_client.users_info.return_value = {"user": {"name": "testuser"}}

        result = check_permission("U12345", mock_client)

        assert result is True
        mock_client.users_info.assert_called_once_with(user="U12345")

    @patch("seosoyoung.main.Config")
    def test_check_permission_denied_user(self, mock_config):
        """허용되지 않은 사용자"""
        mock_config.ALLOWED_USERS = ["allowed_user"]

        mock_client = MagicMock()
        mock_client.users_info.return_value = {"user": {"name": "not_allowed"}}

        result = check_permission("U12345", mock_client)

        assert result is False

    def test_check_permission_api_error(self):
        """API 오류 시 False 반환"""
        mock_client = MagicMock()
        mock_client.users_info.side_effect = Exception("API Error")

        result = check_permission("U12345", mock_client)

        assert result is False


class TestHandleMention:
    """handle_mention 이벤트 핸들러 테스트"""

    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_mention_cc_command(self, mock_check_perm, mock_session_manager):
        """cc 명령어 처리"""
        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> cc",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        # say가 호출되어야 함
        mock_say.assert_called()
        # 세션 생성 확인
        mock_session_manager.create.assert_called_once_with(
            thread_ts="1234567890.123456",
            channel_id="C12345"
        )

    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_mention_help_command(self, mock_check_perm):
        """help 명령어 처리"""
        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> help",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "사용법" in call_text

    @patch("seosoyoung.main.Config")
    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_mention_status_command(self, mock_check_perm, mock_session_manager, mock_config):
        """status 명령어 처리"""
        mock_config.EB_RENPY_PATH = "/path/to/eb_renpy"
        mock_config.ALLOWED_USERS = ["user1", "user2"]
        mock_config.DEBUG = True
        mock_session_manager.count.return_value = 3

        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> status",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "상태" in call_text

    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_mention_unknown_command(self, mock_check_perm):
        """알 수 없는 명령어 처리"""
        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> unknown_command",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "알 수 없는 명령" in call_text

    @patch("seosoyoung.main.check_permission", return_value=False)
    def test_handle_mention_no_permission(self, mock_check_perm):
        """권한 없는 사용자"""
        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> cc",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "권한이 없습니다" in call_text


class TestHandleMessage:
    """handle_message 이벤트 핸들러 테스트"""

    def test_handle_message_bot_message_ignored(self):
        """봇 메시지는 무시"""
        from seosoyoung.main import handle_message

        event = {
            "bot_id": "B12345",
            "user": "U12345",
            "text": "Hello",
            "channel": "C12345",
            "thread_ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # say가 호출되지 않아야 함
        mock_say.assert_not_called()

    def test_handle_message_no_thread_ignored(self):
        """스레드가 아닌 메시지는 무시"""
        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "Hello",
            "channel": "C12345"
            # thread_ts 없음
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        mock_say.assert_not_called()

    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_message_no_session_ignored(self, mock_check_perm, mock_session_manager):
        """세션이 없으면 무시"""
        mock_session_manager.get.return_value = None  # 세션 없음

        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "Hello",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 세션이 없으면 처리 안 함
        mock_say.assert_not_called()

    @patch("seosoyoung.main.check_permission", return_value=False)
    def test_handle_message_no_permission_ignored(self, mock_check_perm):
        """권한 없으면 무시"""
        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "Hello",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        mock_say.assert_not_called()

    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_message_empty_text_ignored(self, mock_check_perm, mock_session_manager):
        """빈 텍스트(멘션만 있는 경우)는 무시"""
        mock_session_manager.get.return_value = MagicMock()

        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "<@UBOT>",  # 멘션만 있음
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 빈 텍스트면 처리 안 함
        mock_client.chat_postMessage.assert_not_called()

    @patch("seosoyoung.main.send_long_message")
    @patch("seosoyoung.main.claude_runner")
    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_message_success(self, mock_check_perm, mock_session_manager, mock_runner, mock_send_long):
        """성공적인 메시지 처리"""
        from seosoyoung.claude.runner import ClaudeResult
        from seosoyoung.main import handle_message

        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session_manager.get.return_value = mock_session

        # Claude 실행 결과
        mock_result = ClaudeResult(
            success=True,
            output="응답입니다",
            session_id="session-123"
        )

        async def mock_run(*args, **kwargs):
            return mock_result

        mock_runner.run = mock_run

        event = {
            "user": "U12345",
            "text": "테스트 메시지",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }

        mock_say = MagicMock()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress-ts"}

        handle_message(event, mock_say, mock_client)

        # on_progress가 호출되지 않으면 chat_postMessage는 호출되지 않음
        # last_message_ts가 None이므로 send_long_message로 최종 응답 전송
        mock_send_long.assert_called()

    @patch("seosoyoung.main.claude_runner")
    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.check_permission", return_value=True)
    def test_handle_message_claude_error(self, mock_check_perm, mock_session_manager, mock_runner):
        """Claude 실행 오류 처리"""
        from seosoyoung.claude.runner import ClaudeResult
        from seosoyoung.main import handle_message

        mock_session = MagicMock()
        mock_session.session_id = "session-123"
        mock_session_manager.get.return_value = mock_session

        # Claude 실행 실패
        mock_result = ClaudeResult(
            success=False,
            output="",
            error="오류 발생"
        )

        async def mock_run(*args, **kwargs):
            return mock_result

        mock_runner.run = mock_run

        event = {
            "user": "U12345",
            "text": "테스트 메시지",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }

        mock_say = MagicMock()
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "progress-ts"}

        handle_message(event, mock_say, mock_client)

        # on_progress가 호출되지 않으면 last_message_ts가 None
        # 따라서 say로 오류 메시지 전송
        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "오류" in call_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
