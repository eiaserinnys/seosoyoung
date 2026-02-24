"""executor.py 유틸리티 함수 테스트"""

from unittest.mock import MagicMock
from seosoyoung.slackbot.claude.message_formatter import (
    build_context_usage_bar,
)
from seosoyoung.slackbot.claude.executor import ClaudeExecutor, ExecutionContext
from seosoyoung.slackbot.claude.session import Session


class TestBuildContextUsageBar:
    """build_context_usage_bar 함수 테스트"""

    def test_none_usage(self):
        """usage가 None이면 None 반환"""
        assert build_context_usage_bar(None) is None

    def test_empty_usage(self):
        """usage가 빈 dict이면 None 반환"""
        assert build_context_usage_bar({}) is None

    def test_zero_tokens(self):
        """토큰이 0이면 None 반환"""
        assert build_context_usage_bar({"input_tokens": 0}) is None

    def test_cache_creation_tokens(self):
        """cache_creation_input_tokens가 컨텍스트에 포함"""
        # 실제 SDK 응답 패턴: input_tokens=3, cache_creation=35000
        usage = {
            "input_tokens": 3,
            "cache_creation_input_tokens": 35000,
            "cache_read_input_tokens": 0,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "18%" in result  # ~35003 / 200000 = 17.5% -> 18%

    def test_cache_read_tokens(self):
        """cache_read_input_tokens가 컨텍스트에 포함"""
        usage = {
            "input_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 39900,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "20%" in result  # 40000 / 200000 = 20%

    def test_all_token_types_combined(self):
        """세 종류 토큰 합산"""
        usage = {
            "input_tokens": 10000,
            "cache_creation_input_tokens": 40000,
            "cache_read_input_tokens": 50000,
        }  # 100k / 200k = 50%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "50%" in result
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 10
        assert empty == 10

    def test_full_usage(self):
        """만석 (100%)"""
        usage = {
            "input_tokens": 1000,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 199000,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result
        assert "□" not in result

    def test_over_capacity(self):
        """초과해도 100%로 캡"""
        usage = {
            "input_tokens": 50000,
            "cache_creation_input_tokens": 100000,
            "cache_read_input_tokens": 100000,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result

    def test_format_structure(self):
        """출력 포맷이 올바른지 확인"""
        usage = {"input_tokens": 60000}  # 30%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert result.startswith("`Context`")
        assert "30%" in result

    def test_only_input_tokens_no_cache(self):
        """cache 키가 없는 경우 input_tokens만으로 계산"""
        usage = {"input_tokens": 40000}  # 20%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "20%" in result

    def test_custom_bar_length(self):
        """bar_length 커스텀"""
        usage = {"input_tokens": 100000}  # 50%
        result = build_context_usage_bar(usage, bar_length=10)
        assert result is not None
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 5
        assert empty == 5

    def test_realistic_sdk_usage(self):
        """실제 SDK 응답 형태의 usage dict"""
        usage = {
            "input_tokens": 3,
            "cache_creation_input_tokens": 35639,
            "cache_read_input_tokens": 0,
            "output_tokens": 11,
            "server_tool_use": {"web_search_requests": 0},
            "service_tier": "standard",
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "18%" in result  # 35642 / 200000 ≈ 17.8% -> 18%


def _make_executor():
    """테스트용 ClaudeExecutor를 간단히 생성"""
    return ClaudeExecutor(
        session_manager=MagicMock(),
        get_session_lock=MagicMock(),
        mark_session_running=MagicMock(),
        mark_session_stopped=MagicMock(),
        get_running_session_count=MagicMock(return_value=1),
        restart_manager=MagicMock(),
        send_long_message=MagicMock(),
        send_restart_confirmation=MagicMock(),
    )


def _make_ctx(is_thread_reply=False, message_count=0, is_existing_thread=False):
    """테스트용 ExecutionContext 생성"""
    session = Session(
        thread_ts="1234.5678",
        channel_id="C_TEST",
        user_id="U_TEST",
        role="admin",
        session_id="test-session",
        message_count=message_count,
    )
    client = MagicMock()
    say = MagicMock()
    ctx = ExecutionContext(
        session=session,
        channel="C_TEST",
        say=say,
        client=client,
        msg_ts="1234.9999",
        effective_role="admin",
        thread_ts="1234.5678",
        is_existing_thread=is_existing_thread,
        is_thread_reply=is_thread_reply,
        last_msg_ts="1234.0001",
    )
    return ctx


def _make_result(output="hello", session_id="test-session", usage=None):
    """가짜 result 객체"""
    result = MagicMock()
    result.output = output
    result.session_id = session_id
    result.usage = usage
    result.interrupted = False
    result.success = True
    result.error = None
    result.update_requested = False
    result.restart_requested = False
    result.list_run = None
    return result


class TestHandleNormalSuccessNoContinuationHint:
    """continuation_hint가 채널 응답에 포함되지 않는지 검증"""

    def test_short_response_no_continuation_hint(self):
        """짧은 응답(3줄 이하)에 continuation_hint 텍스트가 없어야 함"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        result = _make_result(output="한 줄 응답입니다.")

        executor._handle_normal_success(ctx, result, "한 줄 응답입니다.", False, None)

        # chat_update에 전달된 text에 continuation_hint가 없어야 함
        update_call = ctx.client.chat_update.call_args
        assert update_call is not None
        updated_text = update_call.kwargs.get("text", "")
        assert "스레드를 확인해주세요" not in updated_text
        assert "자세한 내용을 확인하시거나" not in updated_text

    def test_long_response_no_continuation_hint(self):
        """긴 응답에도 continuation_hint 텍스트가 없어야 함"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        long_response = "\n".join([f"line {i}" for i in range(10)])
        result = _make_result(output=long_response)

        executor._handle_normal_success(ctx, result, long_response, False, None)

        # chat_update에 전달된 text에 continuation_hint가 없어야 함
        update_call = ctx.client.chat_update.call_args
        assert update_call is not None
        updated_text = update_call.kwargs.get("text", "")
        assert "스레드를 확인해주세요" not in updated_text
        assert "자세한 내용을 확인하시거나" not in updated_text

    def test_thread_reply_no_continuation_hint(self):
        """스레드 내 후속 대화에도 continuation_hint가 없어야 함"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=True)
        result = _make_result(output="스레드 답변")

        executor._handle_normal_success(ctx, result, "스레드 답변", False, None)

        update_call = ctx.client.chat_update.call_args
        assert update_call is not None
        updated_text = update_call.kwargs.get("text", "")
        assert "스레드를 확인해주세요" not in updated_text
        assert "자세한 내용을 확인하시거나" not in updated_text


class TestHandleNormalSuccessShortResponseNoDuplicate:
    """짧은 응답 시 send_long_message가 호출되지 않는지 검증"""

    def test_single_line_no_send_long_message(self):
        """1줄 응답: send_long_message 미호출"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        response = "짧은 응답입니다."
        result = _make_result(output=response)

        executor._handle_normal_success(ctx, result, response, False, None)

        executor.send_long_message.assert_not_called()

    def test_three_lines_no_send_long_message(self):
        """3줄 응답: send_long_message 미호출"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        response = "첫째 줄\n둘째 줄\n셋째 줄"
        result = _make_result(output=response)

        executor._handle_normal_success(ctx, result, response, False, None)

        executor.send_long_message.assert_not_called()

    def test_four_lines_sends_long_message(self):
        """4줄 이상 응답: send_long_message 호출"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        response = "첫째 줄\n둘째 줄\n셋째 줄\n넷째 줄"
        result = _make_result(output=response)

        executor._handle_normal_success(ctx, result, response, False, None)

        executor.send_long_message.assert_called_once()

    def test_many_lines_sends_long_message(self):
        """여러 줄 응답: send_long_message 호출 (전문 전송)"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        response = "\n".join([f"line {i}" for i in range(20)])
        result = _make_result(output=response)

        executor._handle_normal_success(ctx, result, response, False, None)

        executor.send_long_message.assert_called_once()
        # 전문이 전달되어야 함
        call_args = executor.send_long_message.call_args
        assert call_args[0][1] == response  # 두 번째 인자가 전체 응답

    def test_channel_preview_shows_first_3_lines_for_long(self):
        """긴 응답의 채널 미리보기는 3줄 + '...'"""
        executor = _make_executor()
        ctx = _make_ctx(is_thread_reply=False)
        lines = [f"line {i}" for i in range(10)]
        response = "\n".join(lines)
        result = _make_result(output=response)

        executor._handle_normal_success(ctx, result, response, False, None)

        update_call = ctx.client.chat_update.call_args
        updated_text = update_call.kwargs.get("text", "")
        assert "line 0" in updated_text
        assert "line 1" in updated_text
        assert "line 2" in updated_text
        assert "..." in updated_text
        # 4번째 줄은 미리보기에 포함되지 않아야 함
        assert "line 3" not in updated_text
