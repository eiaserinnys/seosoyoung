"""formatting.py 세분화 이벤트 포맷 함수 유닛 테스트

thinking/tool 이벤트의 슬랙 표시 형식을 검증합니다.
"""

import os
import pytest
from unittest.mock import patch

from seosoyoung.slackbot.formatting import (
    _EMOJI_THINKING_DEFAULT,
    _EMOJI_TOOL_DEFAULT,
    _emoji_thinking,
    _emoji_tool,
    PROGRESS_MAX_LEN,
    _summarize_tool_input,
    format_thinking_initial,
    format_thinking_text,
    format_tool_complete,
    format_tool_error,
    format_tool_initial,
)


class TestFormatThinkingInitial:
    """format_thinking_initial 테스트"""

    def test_contains_emoji_and_bold(self):
        result = format_thinking_initial()
        assert _emoji_thinking() in result
        assert "*생각합니다...*" in result

    def test_default_emoji_is_thought_balloon(self):
        """환경변수 미설정 시 기본 이모지는 U+1F4AD"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOULSTREAM_EMOJI_THINKING", None)
            assert _emoji_thinking() == _EMOJI_THINKING_DEFAULT

    def test_custom_emoji_via_env(self):
        """환경변수로 이모지를 오버라이드할 수 있다"""
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_THINKING": ":ssy-thinking:"}):
            result = format_thinking_initial()
            assert ":ssy-thinking:" in result


class TestFormatThinkingText:
    """format_thinking_text 테스트"""

    def test_contains_header_and_quoted_text(self):
        result = format_thinking_text("I need to analyze this")
        assert "*생각합니다...*" in result
        assert "> I need to analyze this" in result

    def test_multiline_text_each_line_quoted(self):
        result = format_thinking_text("line1\nline2\nline3")
        assert "> line1" in result
        assert "> line2" in result
        assert "> line3" in result

    def test_backticks_escaped(self):
        result = format_thinking_text("use `grep` command")
        assert "`" not in result
        assert "grep" in result

    def test_long_text_truncated(self):
        long_text = "x" * (PROGRESS_MAX_LEN + 500)
        result = format_thinking_text(long_text)
        # 헤더 + quote prefix가 추가되므로 원본보다 길지만, 본문은 truncate됨
        assert "..." in result

    def test_empty_text(self):
        result = format_thinking_text("")
        assert "*생각합니다...*" in result
        assert "> " in result


class TestSummarizeToolInput:
    """_summarize_tool_input 테스트"""

    def test_none_returns_empty(self):
        assert _summarize_tool_input(None) == ""

    def test_dict_compacted(self):
        result = _summarize_tool_input({"pattern": "*.py", "path": "/src"})
        assert "pattern" in result
        assert "*.py" in result

    def test_long_input_truncated(self):
        big = {"data": "x" * 500}
        result = _summarize_tool_input(big)
        assert result.endswith("...")
        assert len(result) <= 204  # 200 + "..."

    def test_string_input(self):
        result = _summarize_tool_input("simple string")
        assert result == "simple string"

    def test_empty_dict_compacted(self):
        result = _summarize_tool_input({})
        assert result == "{}"


class TestFormatToolInitial:
    """format_tool_initial 테스트"""

    def test_header_only_without_input(self):
        result = format_tool_initial("Grep")
        assert _emoji_tool() in result
        assert "*Grep*" in result
        assert "\n>" not in result

    def test_header_and_input_with_dict(self):
        result = format_tool_initial("Grep", {"pattern": "hello"})
        assert "*Grep*" in result
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[1].startswith("> ")
        assert "hello" in lines[1]

    def test_none_input_same_as_no_input(self):
        result_none = format_tool_initial("Read", None)
        result_no_arg = format_tool_initial("Read")
        assert result_none == result_no_arg

    def test_empty_dict_input_no_quote(self):
        """빈 dict는 falsy이므로 input 줄이 표시되지 않음"""
        result = format_tool_initial("Bash", {})
        assert "\n>" not in result


class TestFormatToolComplete:
    """format_tool_complete 테스트"""

    def test_contains_emoji_and_done(self):
        result = format_tool_complete("Grep")
        assert _emoji_tool() in result
        assert "*Grep*" in result
        assert "(done)" in result


class TestFormatToolError:
    """format_tool_error 테스트"""

    def test_contains_emoji_and_error(self):
        result = format_tool_error("Bash", "command failed")
        assert _emoji_tool() in result
        assert "*Bash*" in result
        assert ":x:" in result
        assert "command failed" in result

    def test_backticks_in_error_escaped(self):
        result = format_tool_error("Bash", "error in `main`")
        assert "`" not in result
        assert "main" in result
