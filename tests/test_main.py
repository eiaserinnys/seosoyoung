"""Main 모듈 테스트

리팩터링 후 각 모듈에서 함수를 import합니다.
"""

from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

# 리팩터링된 모듈에서 import
from seosoyoung.handlers.mention import extract_command, get_channel_history
from seosoyoung.slack.helpers import send_long_message
from seosoyoung.auth import check_permission, get_user_role
from seosoyoung.claude.executor import get_runner_for_role
from seosoyoung.claude.message_formatter import escape_backticks, build_trello_header
from seosoyoung.trello.watcher import TrackedCard


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

    @patch("seosoyoung.auth.Config")
    def test_check_permission_allowed_user(self, mock_config):
        """허용된 사용자"""
        mock_config.ALLOWED_USERS = ["testuser"]

        mock_client = MagicMock()
        mock_client.users_info.return_value = {"user": {"name": "testuser"}}

        result = check_permission("U12345", mock_client)

        assert result is True
        mock_client.users_info.assert_called_once_with(user="U12345")

    @patch("seosoyoung.auth.Config")
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

    @patch("seosoyoung.auth.Config")
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

    @patch("seosoyoung.auth.Config")
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

    @patch("seosoyoung.claude.executor._get_mcp_config_path", return_value=Path("mcp_config.json"))
    @patch("seosoyoung.claude.executor.Config")
    @patch("seosoyoung.claude.executor.get_claude_runner")
    def test_get_runner_for_admin(self, mock_get_runner, mock_config, mock_mcp_path):
        """관리자 역할용 runner"""
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            "viewer": ["Read", "Glob", "Grep"]
        }

        get_runner_for_role("admin")

        # admin은 disallowed_tools 없이, mcp_config_path + cache_key 포함하여 생성
        mock_get_runner.assert_called_once_with(
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            mcp_config_path=Path("mcp_config.json"),
            cache_key="role:admin",
        )

    @patch("seosoyoung.claude.executor.Config")
    @patch("seosoyoung.claude.executor.get_claude_runner")
    def test_get_runner_for_viewer(self, mock_get_runner, mock_config):
        """일반 사용자 역할용 runner"""
        mock_config.ROLE_TOOLS = {
            "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            "viewer": ["Read", "Glob", "Grep"]
        }

        get_runner_for_role("viewer")

        # viewer는 수정 도구들이 차단됨
        mock_get_runner.assert_called_once_with(
            allowed_tools=["Read", "Glob", "Grep"],
            disallowed_tools=["Write", "Edit", "Bash", "TodoWrite", "WebFetch", "WebSearch", "Task"],
            cache_key="role:viewer",
        )


class TestGetChannelHistory:
    """get_channel_history 함수 테스트"""

    def test_get_channel_history_success(self):
        """채널 히스토리 가져오기 성공"""
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
        mock_client = MagicMock()
        mock_client.conversations_history.side_effect = Exception("API Error")

        result = get_channel_history(mock_client, "C12345")

        assert result == ""


class TestEscapeBackticks:
    """escape_backticks 함수 테스트 - 모든 백틱 이스케이프"""

    def test_single_backtick_escaped(self):
        """단일 백틱도 이스케이프"""
        result = escape_backticks("Hello `world`")
        assert result == "Hello ˋworldˋ"
        assert "`" not in result

    def test_double_backtick_escaped(self):
        """이중 백틱 이스케이프"""
        result = escape_backticks("Use ``code`` here")
        assert result == "Use ˋˋcodeˋˋ here"
        assert "`" not in result

    def test_triple_backticks_escaped(self):
        """삼중 백틱(코드 블록)은 이스케이프"""
        result = escape_backticks("```python\nprint('hello')\n```")
        assert "`" not in result
        assert "ˋˋˋ" in result
        assert "print('hello')" in result

    def test_quadruple_backticks_escaped(self):
        """4개 백틱도 이스케이프"""
        result = escape_backticks("````markdown\n# Title\n````")
        assert "`" not in result
        assert "ˋˋˋˋ" in result

    def test_mixed_backticks(self):
        """혼합된 백틱 패턴"""
        text = "Use `inline` and ```block``` code"
        result = escape_backticks(text)
        assert "`" not in result  # 모든 백틱 이스케이프
        assert "ˋinlineˋ" in result
        assert "ˋˋˋblockˋˋˋ" in result

    def test_no_backticks(self):
        """백틱이 없는 텍스트"""
        result = escape_backticks("Hello world")
        assert result == "Hello world"

    def test_empty_string(self):
        """빈 문자열"""
        result = escape_backticks("")
        assert result == ""

    def test_code_block_with_language(self):
        """언어 지정된 코드 블록"""
        text = "```javascript\nconst x = 1;\n```"
        result = escape_backticks(text)
        assert "`" not in result
        assert "ˋˋˋjavascript" in result
        assert "const x = 1;" in result

    def test_nested_code_blocks(self):
        """중첩된 코드 블록 (마크다운 내 코드 블록 설명)"""
        text = """Here's how to write code:
```markdown
Use triple backticks:
```python
print("hello")
```
```"""
        result = escape_backticks(text)
        assert "`" not in result
        # 모든 삼중 백틱이 이스케이프되어야 함
        assert result.count("ˋˋˋ") >= 3

    def test_code_block_in_explanation(self):
        """Claude가 코드 블록 사용법을 설명하는 경우"""
        text = """파일을 수정했습니다:
```python
def hello():
    print("world")
```

다음 명령어로 실행하세요:
```bash
python main.py
```"""
        result = escape_backticks(text)
        assert "`" not in result
        assert result.count("ˋˋˋ") == 4  # 시작/끝 각 2개씩

    def test_backticks_at_line_start(self):
        """줄 시작에 백틱이 있는 경우"""
        text = "설명:\n```\ncode here\n```"
        result = escape_backticks(text)
        assert "`" not in result

    def test_consecutive_code_blocks(self):
        """연속된 코드 블록"""
        text = "```\nblock1\n``````\nblock2\n```"
        result = escape_backticks(text)
        assert "`" not in result
        # 6개 연속 백틱도 처리
        assert "ˋˋˋˋˋˋ" in result

    def test_real_claude_response_simulation(self):
        """실제 Claude 응답 시뮬레이션"""
        text = """파일을 확인했습니다.

`config.py`에서 다음 설정을 찾았습니다:

```python
DEBUG = True
API_KEY = "..."
```

그리고 `main.py`에서:

```python
from config import DEBUG
if DEBUG:
    print("Debug mode")
```

수정이 필요하시면 말씀해주세요."""
        result = escape_backticks(text)
        # 모든 백틱이 이스케이프됨
        assert "`" not in result
        assert "ˋconfig.pyˋ" in result
        assert "ˋmain.pyˋ" in result
        assert result.count("ˋˋˋ") == 4

    def test_only_backticks(self):
        """백틱만 있는 경우"""
        result = escape_backticks("```")
        assert result == "ˋˋˋ"

    def test_many_consecutive_backticks(self):
        """매우 많은 연속 백틱"""
        result = escape_backticks("``````````")  # 10개
        assert "`" not in result
        assert "ˋ" * 10 == result

    def test_special_characters_preserved(self):
        """특수 문자는 영향 없음"""
        text = "```\n<>&\"'\n```"
        result = escape_backticks(text)
        assert "<>&\"'" in result

    def test_unicode_preserved(self):
        """유니코드 문자 보존"""
        text = "```\n한글 테스트 🎉\n```"
        result = escape_backticks(text)
        assert "한글 테스트 🎉" in result
        assert "`" not in result


class TestBuildTrelloHeader:
    """build_trello_header 함수 테스트

    NOTE: mode 파라미터가 제거됨 (진행 상태는 슬랙 이모지 리액션으로 표시)
    """

    def _create_tracked_card(self, **kwargs):
        """테스트용 TrackedCard 생성"""
        defaults = {
            "card_id": "test_card_id",
            "card_name": "테스트 카드",
            "card_url": "https://trello.com/c/abc123",
            "list_id": "test_list_id",
            "list_key": "to_go",
            "thread_ts": "1234567890.123456",
            "channel_id": "C12345",
            "detected_at": "2024-01-01T00:00:00",
            "session_id": None,
            "has_execute": False,
        }
        defaults.update(kwargs)
        return TrackedCard(**defaults)

    def test_header_basic(self):
        """기본 헤더 생성 (모드 없음)"""
        card = self._create_tracked_card()
        result = build_trello_header(card)

        assert "🎫" in result
        assert "테스트 카드" in result
        # 모드 이모지/텍스트가 없어야 함
        assert "💭" not in result
        assert "▶️" not in result
        assert "✅" not in result
        assert "계획 중" not in result
        assert "실행 중" not in result
        assert "완료" not in result

    def test_header_no_mode_emoji(self):
        """헤더에 모드 이모지가 포함되지 않음"""
        card = self._create_tracked_card()
        result = build_trello_header(card)

        # 모드 관련 이모지가 없어야 함
        assert "💭" not in result
        assert "▶️" not in result

    def test_header_no_mode_text(self):
        """헤더에 모드 텍스트가 포함되지 않음"""
        card = self._create_tracked_card()
        result = build_trello_header(card)

        assert "계획 중" not in result
        assert "실행 중" not in result
        assert "완료" not in result

    def test_header_with_session_id(self):
        """세션 ID가 있는 헤더"""
        card = self._create_tracked_card()
        result = build_trello_header(card, session_id="abcd1234efgh5678")

        assert "#️⃣" in result
        assert "abcd1234" in result  # 8자까지만 표시

    def test_header_without_session_id(self):
        """세션 ID가 없는 헤더"""
        card = self._create_tracked_card()
        result = build_trello_header(card, session_id="")

        assert "#️⃣" not in result

    def test_header_contains_card_link(self):
        """헤더에 카드 링크 포함"""
        card = self._create_tracked_card()
        result = build_trello_header(card)

        assert "https://trello.com/c/abc123" in result
        assert "<https://trello.com/c/abc123|테스트 카드>" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
