"""rescue-bot 테스트

메인 봇의 test_agent_runner.py 핵심 테스트를 rescue 전용으로 복제합니다.
"""

import asyncio
import os
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# SDK 메시지 타입 Mock (메인 봇 테스트와 동일 패턴)
@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list = None


@dataclass
class MockResultMessage:
    result: str = ""
    session_id: str = None


def _make_mock_client(*messages):
    """mock_receive async generator를 설정한 mock client를 생성하는 헬퍼"""
    mock_client = AsyncMock()

    async def mock_receive():
        for msg in messages:
            yield msg

    mock_client.receive_response = mock_receive
    return mock_client


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


class TestClassifyProcessError:
    """_classify_process_error 테스트 (메인 봇 동일 시리즈)"""

    def test_usage_limit_keyword(self):
        """usage limit 키워드 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=1, stderr="usage limit reached")
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_rate_limit_keyword(self):
        """rate limit 키워드 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("rate limit exceeded", exit_code=1, stderr=None)
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_429_status(self):
        """429 상태 코드 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=1, stderr="HTTP 429 Too Many Requests")
        msg = _classify_process_error(e)
        assert "사용량 제한" in msg

    def test_unauthorized_401(self):
        """401 인증 오류 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=1, stderr="401 Unauthorized")
        msg = _classify_process_error(e)
        assert "인증" in msg

    def test_forbidden_403(self):
        """403 권한 오류 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=1, stderr="403 Forbidden")
        msg = _classify_process_error(e)
        assert "인증" in msg

    def test_network_error(self):
        """네트워크 오류 감지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Connection refused", exit_code=1, stderr="ECONNREFUSED")
        msg = _classify_process_error(e)
        assert "네트워크" in msg

    def test_generic_exit_code_1(self):
        """exit code 1 일반 폴백"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details")
        msg = _classify_process_error(e)
        assert "비정상 종료" in msg
        assert "잠시 후" in msg

    def test_other_exit_code(self):
        """기타 exit code"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=137, stderr=None)
        msg = _classify_process_error(e)
        assert "exit code: 137" in msg

    def test_none_stderr(self):
        """stderr가 None인 경우"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import _classify_process_error

        e = ProcessError("Command failed", exit_code=1, stderr=None)
        msg = _classify_process_error(e)
        assert "비정상 종료" in msg


class TestBuildOptions:
    """_build_options 테스트"""

    def test_build_options_basic(self):
        """기본 옵션 생성"""
        from seosoyoung.rescue.runner import ALLOWED_TOOLS, DISALLOWED_TOOLS, RescueRunner

        runner = RescueRunner()
        options = runner._build_options()

        assert options.allowed_tools == ALLOWED_TOOLS
        assert options.disallowed_tools == DISALLOWED_TOOLS
        assert options.permission_mode == "bypassPermissions"
        assert options.resume is None

    def test_build_options_with_session(self):
        """세션 ID가 있을 때 resume 옵션 추가"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()
        options = runner._build_options(session_id="abc-123")

        assert options.resume == "abc-123"


@pytest.mark.asyncio
class TestRescueRunnerAsync:
    """비동기 테스트 (ClaudeSDKClient Mock 사용)"""

    async def test_run_success(self):
        """성공적인 SDK 실행 테스트"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="test-sdk-123"),
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료되었습니다.", session_id="test-sdk-123"),
        )

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.rescue.runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.rescue.runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.rescue.runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.rescue.runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트 프롬프트")

        assert result.success is True
        assert result.session_id == "test-sdk-123"
        assert "완료되었습니다" in result.output

    async def test_run_with_resume(self):
        """세션 재개 시 resume 옵션 전달 확인"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="이어진 응답", session_id="test-session-123"),
        )

        captured_options = {}

        original_build = runner._build_options

        def capture_build(session_id=None):
            opts = original_build(session_id=session_id)
            captured_options["options"] = opts
            return opts

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.rescue.runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", capture_build):
                    result = await runner.run("후속 질문", session_id="test-session-123")

        assert result.success is True
        assert result.output == "이어진 응답"
        assert captured_options["options"].resume == "test-session-123"

    async def test_run_timeout(self):
        """idle 타임아웃 테스트"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()

        async def mock_receive_slow():
            yield MockSystemMessage(session_id="timeout-test")
            await asyncio.sleep(10)
            yield MockResultMessage(result="이건 도달 안 됨")

        mock_client.receive_response = mock_receive_slow

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.rescue.runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.rescue.runner.RescueConfig") as mock_config:
                    mock_config.CLAUDE_TIMEOUT = 1
                    mock_config.get_working_dir.return_value = __import__("pathlib").Path.cwd()
                    result = await runner.run("테스트")

        assert result.success is False
        assert "타임아웃" in result.error

    async def test_run_file_not_found(self):
        """Claude CLI 없음 테스트"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = FileNotFoundError("claude not found")

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error

    async def test_run_general_exception(self):
        """일반 예외 처리 테스트"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = RuntimeError("SDK error")

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "SDK error" in result.error

    async def test_concurrent_execution_blocked(self):
        """동시 실행 제어 테스트 (Lock)"""
        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()
        call_order = []

        def make_ordered_client(label):
            mock_client = AsyncMock()

            async def mock_receive():
                call_order.append(f"start-{label}")
                await asyncio.sleep(0.1)
                call_order.append(f"end-{label}")
                yield MockResultMessage(result="done", session_id="test")

            mock_client.receive_response = mock_receive
            return mock_client

        clients = [make_ordered_client("1"), make_ordered_client("2")]
        client_idx = [0]

        def get_next_client(*args, **kwargs):
            c = clients[client_idx[0]]
            client_idx[0] += 1
            return c

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", side_effect=get_next_client):
            with patch("seosoyoung.rescue.runner.ResultMessage", MockResultMessage):
                task1 = asyncio.create_task(runner.run("first"))
                task2 = asyncio.create_task(runner.run("second"))
                await asyncio.gather(task1, task2)

        # Lock으로 인해 순차 실행
        assert call_order == ["start-1", "end-1", "start-2", "end-2"]

    async def test_run_claude_sync(self):
        """run_claude_sync 동기 브릿지 테스트"""
        from seosoyoung.rescue.runner import RescueResult, RescueRunner

        runner = RescueRunner()
        expected = RescueResult(success=True, output="동기 결과", session_id="sync-123")

        with patch.object(runner, "run", new_callable=AsyncMock, return_value=expected):
            with patch.object(runner, "_ensure_loop"):
                with patch.object(runner, "run_sync", return_value=expected):
                    result = runner.run_claude_sync("테스트")

        assert result.success is True
        assert result.output == "동기 결과"


@pytest.mark.asyncio
class TestProcessErrorHandling:
    """ProcessError가 _execute에서 올바르게 처리되는지 테스트"""

    async def test_process_error_returns_friendly_message(self):
        """ProcessError 발생 시 친절한 메시지 반환"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "Command failed with exit code 1", exit_code=1, stderr="Check stderr output for details"
        )

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "비정상 종료" in result.error
        assert "잠시 후" in result.error
        assert "Command failed" not in result.error

    async def test_process_error_with_usage_limit(self):
        """usage limit ProcessError 발생 시 친절한 메시지"""
        from claude_code_sdk._errors import ProcessError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = ProcessError(
            "usage limit reached", exit_code=1, stderr="usage limit"
        )

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error


@pytest.mark.asyncio
class TestRateLimitEventHandling:
    """rate_limit_event (MessageParseError) 처리 테스트"""

    async def test_rate_limit_event_retries_and_continues(self):
        """rate_limit_event 1회 후 정상 종료되면 success"""
        from claude_code_sdk._errors import MessageParseError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()

        class MockAsyncIter:
            def __init__(self):
                self.raised = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.raised:
                    self.raised = True
                    raise MessageParseError(
                        "Unknown message type: rate_limit_event",
                        {"type": "rate_limit_event"},
                    )
                raise StopAsyncIteration

        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=MockAsyncIter())
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await runner.run("테스트")

        assert result.success is True
        mock_sleep.assert_called_with(1)

    async def test_rate_limit_event_max_retries_exceeded(self):
        """rate_limit_event 3회 초과 시 친화적 에러 반환"""
        from claude_code_sdk._errors import MessageParseError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()

        class MockAsyncIterAlwaysRateLimit:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise MessageParseError(
                    "Unknown message type: rate_limit_event",
                    {"type": "rate_limit_event"},
                )

        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = MagicMock(return_value=MockAsyncIterAlwaysRateLimit())
        mock_client.disconnect = AsyncMock()

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error
        assert mock_sleep.call_count == 3

    async def test_rate_limit_event_returns_friendly_error(self):
        """rate_limit_event가 외부 except에서 잡힐 때 친화적 메시지 반환"""
        from claude_code_sdk._errors import MessageParseError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: rate_limit_event",
            {"type": "rate_limit_event"},
        )

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "사용량 제한" in result.error
        assert "Unknown message type" not in result.error

    async def test_non_rate_limit_parse_error_returns_friendly_error(self):
        """rate_limit이 아닌 MessageParseError도 친화적 메시지 반환"""
        from claude_code_sdk._errors import MessageParseError

        from seosoyoung.rescue.runner import RescueRunner

        runner = RescueRunner()

        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.query = AsyncMock()
        mock_client.disconnect = AsyncMock()

        mock_client.connect.side_effect = MessageParseError(
            "Unknown message type: some_unknown_type",
            {"type": "some_unknown_type"},
        )

        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "오류가 발생했습니다" in result.error
        assert "Unknown message type" not in result.error


class TestRescueRunnerClient:
    """클라이언트 생명주기 테스트"""

    def test_get_or_create_client_reuse(self):
        """같은 키로 호출하면 기존 클라이언트를 재사용"""
        from seosoyoung.rescue.runner import RescueRunner

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        runner = RescueRunner()

        async def _test():
            with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
                options = MagicMock()
                c1 = await runner._get_or_create_client("key1", options)
                c2 = await runner._get_or_create_client("key1", options)
                assert c1 is c2
                mock_client.connect.assert_awaited_once()

        asyncio.run(_test())

    def test_remove_client(self):
        """_remove_client가 disconnect를 호출하고 딕셔너리에서 제거"""
        from seosoyoung.rescue.runner import RescueRunner

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        runner = RescueRunner()

        async def _test():
            with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
                options = MagicMock()
                await runner._get_or_create_client("key1", options)
                assert "key1" in runner._active_clients
                await runner._remove_client("key1")
                assert "key1" not in runner._active_clients
                mock_client.disconnect.assert_awaited_once()

        asyncio.run(_test())

    def test_execute_disconnect_on_success(self):
        """성공 후 disconnect가 호출되는지 확인"""
        from claude_code_sdk.types import ResultMessage

        from seosoyoung.rescue.runner import RescueRunner

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

        runner = RescueRunner()
        with patch("seosoyoung.rescue.runner.ClaudeSDKClient", return_value=mock_client):
            asyncio.run(runner._execute("테스트"))
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

            assert _get_session_id("5555.6666") == "new-session-id"
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
