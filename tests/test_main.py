"""Main 모듈 테스트"""

import pytest
from unittest.mock import MagicMock, patch

# conftest.py에서 환경 변수가 설정되므로 import 가능
from seosoyoung.main import (
    extract_command,
    send_long_message,
    check_permission,
    get_user_role,
    get_runner_for_role,
)


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
        result = extract_command("<@U12345>   status  ")
        assert result == "status"

    def test_extract_command_empty(self):
        """빈 명령어"""
        result = extract_command("<@U12345>")
        assert result == ""

    def test_extract_command_multiple_mentions(self):
        """여러 멘션이 있는 경우"""
        result = extract_command("<@U12345> <@U67890> status")
        assert result == "status"

    def test_extract_command_question(self):
        """일반 질문 (명령어 아님)"""
        result = extract_command("<@U12345> 오늘 날씨 어때?")
        assert result == "오늘 날씨 어때?"


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


class TestGetUserRole:
    """get_user_role 함수 테스트"""

    @patch("seosoyoung.main.Config")
    def test_get_user_role_admin(self, mock_config):
        """관리자 사용자 역할"""
        mock_config.ADMIN_USERS = ["admin_user"]
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit"],
            "viewer": ["Read"]
        }

        mock_client = MagicMock()
        mock_client.users_info.return_value = {"user": {"name": "admin_user"}}

        result = get_user_role("U12345", mock_client)

        assert result is not None
        assert result["role"] == "admin"
        assert result["username"] == "admin_user"
        assert result["user_id"] == "U12345"
        assert result["allowed_tools"] == ["Read", "Write", "Edit"]

    @patch("seosoyoung.main.Config")
    def test_get_user_role_viewer(self, mock_config):
        """일반 사용자 역할 (viewer)"""
        mock_config.ADMIN_USERS = ["admin_user"]
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit"],
            "viewer": ["Read"]
        }

        mock_client = MagicMock()
        mock_client.users_info.return_value = {"user": {"name": "regular_user"}}

        result = get_user_role("U12345", mock_client)

        assert result is not None
        assert result["role"] == "viewer"
        assert result["username"] == "regular_user"
        assert result["allowed_tools"] == ["Read"]

    def test_get_user_role_api_error(self):
        """API 오류 시 None 반환"""
        mock_client = MagicMock()
        mock_client.users_info.side_effect = Exception("API Error")

        result = get_user_role("U12345", mock_client)

        assert result is None


class TestGetRunnerForRole:
    """get_runner_for_role 함수 테스트"""

    @patch("seosoyoung.main.Config")
    @patch("seosoyoung.main.ClaudeRunner")
    def test_get_runner_for_admin(self, mock_runner_class, mock_config):
        """관리자 역할용 runner"""
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            "viewer": ["Read", "Glob", "Grep"]
        }

        get_runner_for_role("admin")

        # admin은 disallowed_tools 없이 생성
        mock_runner_class.assert_called_once_with(
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"]
        )

    @patch("seosoyoung.main.Config")
    @patch("seosoyoung.main.ClaudeRunner")
    def test_get_runner_for_viewer(self, mock_runner_class, mock_config):
        """일반 사용자 역할용 runner"""
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            "viewer": ["Read", "Glob", "Grep"]
        }

        get_runner_for_role("viewer")

        # viewer는 수정 도구들이 차단됨
        mock_runner_class.assert_called_once_with(
            allowed_tools=["Read", "Glob", "Grep"],
            disallowed_tools=["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"]
        )


class TestHandleMention:
    """handle_mention 이벤트 핸들러 테스트"""

    def test_handle_mention_help_command(self):
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
    def test_handle_mention_status_command(self, mock_session_manager, mock_config):
        """status 명령어 처리"""
        mock_config.EB_RENPY_PATH = "/path/to/eb_renpy"
        mock_config.ADMIN_USERS = ["user1", "user2"]
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

    @patch("seosoyoung.main.check_permission", return_value=False)
    def test_handle_mention_update_no_permission(self, mock_check_perm):
        """update 명령어 - 권한 없음"""
        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> update",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        mock_say.assert_called()
        call_text = mock_say.call_args.kwargs["text"]
        assert "관리자 권한" in call_text

    @patch("seosoyoung.main._run_claude_in_session")
    @patch("seosoyoung.main.get_channel_history", return_value="<U123>: 이전 대화")
    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.get_user_role")
    def test_handle_mention_question_creates_session(
        self, mock_get_role, mock_session_manager, mock_history, mock_run_claude
    ):
        """일반 질문은 세션 생성 후 Claude 실행"""
        mock_get_role.return_value = {
            "user_id": "U12345",
            "username": "testuser",
            "role": "viewer",
            "allowed_tools": ["Read", "Glob", "Grep"]
        }
        mock_session = MagicMock()
        mock_session_manager.create.return_value = mock_session

        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> rev1의 대사 구조를 설명해줘",
            "channel": "C12345",
            "ts": "1234567890.123456"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        # 세션 생성 확인
        mock_session_manager.create.assert_called_once()
        call_kwargs = mock_session_manager.create.call_args.kwargs
        assert call_kwargs["thread_ts"] == "1234567890.123456"
        assert call_kwargs["role"] == "viewer"
        assert call_kwargs["username"] == "testuser"

        # Claude 실행 확인
        mock_run_claude.assert_called_once()

    @patch("seosoyoung.main.session_manager")
    def test_handle_mention_in_thread_with_session_ignored(self, mock_session_manager):
        """세션이 있는 스레드에서 멘션은 무시 (handle_message에서 처리)"""
        mock_session_manager.exists.return_value = True

        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> 추가 질문입니다",
            "channel": "C12345",
            "ts": "1234567890.123457",
            "thread_ts": "1234567890.123456"  # 스레드 내 멘션
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        # 세션이 있으면 무시 (handle_message에서 처리)
        mock_say.assert_not_called()

    @patch("seosoyoung.main._run_claude_in_session")
    @patch("seosoyoung.main.get_channel_history", return_value="")
    @patch("seosoyoung.main.session_manager")
    @patch("seosoyoung.main.get_user_role")
    def test_handle_mention_in_thread_without_session_oneshot(
        self, mock_get_role, mock_session_manager, mock_history, mock_run_claude
    ):
        """세션이 없는 스레드에서 멘션은 원샷 답변"""
        mock_session_manager.exists.return_value = False
        mock_get_role.return_value = {
            "user_id": "U12345",
            "username": "testuser",
            "role": "viewer",
            "allowed_tools": ["Read", "Glob", "Grep"]
        }
        mock_session = MagicMock()
        mock_session_manager.create.return_value = mock_session

        from seosoyoung.main import handle_mention

        event = {
            "user": "U12345",
            "text": "<@UBOT> 이 스레드에서 질문합니다",
            "channel": "C12345",
            "ts": "1234567890.123457",
            "thread_ts": "1234567890.123456"  # 세션 없는 스레드
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_mention(event, mock_say, mock_client)

        # 세션이 thread_ts 기준으로 생성됨
        call_kwargs = mock_session_manager.create.call_args.kwargs
        assert call_kwargs["thread_ts"] == "1234567890.123456"

        # 스레드 시작 메시지 없음 (원샷)
        # 바로 Claude 실행
        mock_run_claude.assert_called_once()


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

    def test_handle_message_with_mention_ignored(self):
        """멘션이 포함된 메시지는 무시 (handle_mention에서 처리)"""
        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "<@UBOT> 질문입니다",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 멘션이 있으면 무시
        mock_say.assert_not_called()

    @patch("seosoyoung.main.session_manager")
    def test_handle_message_no_session_ignored(self, mock_session_manager):
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

    @patch("seosoyoung.main._run_claude_in_session")
    @patch("seosoyoung.main.get_user_role")
    @patch("seosoyoung.main.session_manager")
    def test_handle_message_with_session_runs_claude(self, mock_session_manager, mock_get_role, mock_run_claude):
        """세션이 있으면 Claude 실행"""
        mock_session = MagicMock()
        mock_session.role = "admin"
        mock_session_manager.get.return_value = mock_session
        mock_get_role.return_value = {
            "user_id": "U12345",
            "username": "testuser",
            "role": "admin",
            "allowed_tools": ["Read", "Write", "Edit"]
        }

        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "파일 구조를 보여줘",  # 멘션 없음
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # Claude 실행 확인
        mock_run_claude.assert_called_once()
        call_args = mock_run_claude.call_args
        assert call_args[0][0] == mock_session  # 첫 번째 인자: session
        assert call_args[0][1] == "파일 구조를 보여줘"  # 두 번째 인자: prompt
        assert call_args.kwargs.get("role") == "admin"  # 역할 파라미터

    @patch("seosoyoung.main._run_claude_in_session")
    @patch("seosoyoung.main.get_user_role")
    @patch("seosoyoung.main.session_manager")
    def test_handle_message_uses_message_author_role(self, mock_session_manager, mock_get_role, mock_run_claude):
        """스레드 메시지는 세션 생성자가 아닌 메시지 작성자 권한으로 실행"""
        # 세션은 admin이 생성했지만
        mock_session = MagicMock()
        mock_session.role = "admin"
        mock_session.user_id = "U_ADMIN"
        mock_session_manager.get.return_value = mock_session

        # 메시지 작성자는 viewer
        mock_get_role.return_value = {
            "user_id": "U_VIEWER",
            "username": "viewer_user",
            "role": "viewer",
            "allowed_tools": ["Read", "Glob", "Grep"]
        }

        from seosoyoung.main import handle_message

        event = {
            "user": "U_VIEWER",  # admin이 아닌 다른 사용자
            "text": "파일 수정해줘",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 메시지 작성자 역할 조회 확인
        mock_get_role.assert_called_once_with("U_VIEWER", mock_client)

        # viewer 권한으로 실행되어야 함
        mock_run_claude.assert_called_once()
        call_args = mock_run_claude.call_args
        assert call_args.kwargs.get("role") == "viewer"

    @patch("seosoyoung.main._run_claude_in_session")
    @patch("seosoyoung.main.get_user_role")
    @patch("seosoyoung.main.session_manager")
    def test_handle_message_user_info_error(self, mock_session_manager, mock_get_role, mock_run_claude):
        """사용자 정보 조회 실패 시 에러 메시지"""
        mock_session = MagicMock()
        mock_session_manager.get.return_value = mock_session
        mock_get_role.return_value = None  # 사용자 정보 조회 실패

        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "테스트 메시지",
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 에러 메시지 전송
        mock_say.assert_called_once()
        assert "사용자 정보" in mock_say.call_args.kwargs["text"]

        # Claude는 실행되지 않음
        mock_run_claude.assert_not_called()

    @patch("seosoyoung.main.session_manager")
    def test_handle_message_empty_text_ignored(self, mock_session_manager):
        """빈 텍스트는 무시"""
        mock_session = MagicMock()
        mock_session_manager.get.return_value = mock_session

        from seosoyoung.main import handle_message

        event = {
            "user": "U12345",
            "text": "",  # 빈 텍스트
            "channel": "C12345",
            "thread_ts": "1234567890.123456",
            "ts": "1234567890.123457"
        }
        mock_say = MagicMock()
        mock_client = MagicMock()

        handle_message(event, mock_say, mock_client)

        # 빈 텍스트면 처리 안 함
        mock_say.assert_not_called()


class TestGetChannelHistory:
    """get_channel_history 함수 테스트"""

    def test_get_channel_history_success(self):
        """채널 히스토리 가져오기 성공"""
        from seosoyoung.main import get_channel_history

        mock_client = MagicMock()
        mock_client.conversations_history.return_value = {
            "messages": [
                {"user": "U123", "text": "첫 번째 메시지"},
                {"user": "U456", "text": "두 번째 메시지"},
            ]
        }

        result = get_channel_history(mock_client, "C12345", limit=20)

        mock_client.conversations_history.assert_called_once_with(channel="C12345", limit=20)
        # 시간순 정렬 (오래된 것부터)
        assert "<U456>: 두 번째 메시지" in result
        assert "<U123>: 첫 번째 메시지" in result

    def test_get_channel_history_api_error(self):
        """API 오류 시 빈 문자열 반환"""
        from seosoyoung.main import get_channel_history

        mock_client = MagicMock()
        mock_client.conversations_history.side_effect = Exception("API Error")

        result = get_channel_history(mock_client, "C12345")

        assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
