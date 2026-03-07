"""formatting.py 세분화 이벤트 포맷 함수 유닛 테스트

thinking/tool 이벤트의 슬랙 표시 형식을 검증합니다.
"""

import os
from unittest.mock import patch

from seosoyoung.slackbot.formatting import (
    _EMOJI_THINKING_DEFAULT,
    _EMOJI_THINKING_DONE_DEFAULT,
    _EMOJI_TOOL_DEFAULT,
    _EMOJI_TOOL_DONE_DEFAULT,
    THINKING_QUOTE_MAX_LEN,
    TOOL_INPUT_QUOTE_MAX_LEN,
    TOOL_RESULT_MAX_LEN,
    _emoji_thinking,
    _emoji_thinking_done,
    _emoji_tool,
    _emoji_tool_done,
    _format_tool_input_readable,
    _normalize_newlines,
    _quote_lines,
    format_initial_placeholder,
    format_thinking_complete,
    format_thinking_initial,
    format_thinking_text,
    format_tool_complete,
    format_tool_initial,
    format_tool_result,
)


class TestEmojiDefaults:
    """이모지 기본값과 환경변수 오버라이드 테스트"""

    def test_thinking_default_is_slack_standard(self):
        assert _EMOJI_THINKING_DEFAULT == ":thought_balloon:"

    def test_tool_default_is_slack_standard(self):
        assert _EMOJI_TOOL_DEFAULT == ":hammer:"

    def test_thinking_done_default(self):
        assert _EMOJI_THINKING_DONE_DEFAULT == ":white_check_mark:"

    def test_tool_done_default(self):
        assert _EMOJI_TOOL_DONE_DEFAULT == ":white_check_mark:"

    def test_thinking_emoji_env_override(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_THINKING": ":ssy-thinking:"}):
            assert _emoji_thinking() == ":ssy-thinking:"

    def test_tool_emoji_env_override(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_TOOL": ":ssy-tool:"}):
            assert _emoji_tool() == ":ssy-tool:"

    def test_thinking_done_emoji_env_override(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_THINKING_DONE": ":ssy-happy:"}):
            assert _emoji_thinking_done() == ":ssy-happy:"

    def test_tool_done_emoji_env_override(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_TOOL_DONE": ":ssy-done:"}):
            assert _emoji_tool_done() == ":ssy-done:"

    def test_default_when_env_unset(self):
        for var in [
            "SOULSTREAM_EMOJI_THINKING",
            "SOULSTREAM_EMOJI_TOOL",
            "SOULSTREAM_EMOJI_THINKING_DONE",
            "SOULSTREAM_EMOJI_TOOL_DONE",
        ]:
            os.environ.pop(var, None)
        assert _emoji_thinking() == _EMOJI_THINKING_DEFAULT
        assert _emoji_tool() == _EMOJI_TOOL_DEFAULT
        assert _emoji_thinking_done() == _EMOJI_THINKING_DONE_DEFAULT
        assert _emoji_tool_done() == _EMOJI_TOOL_DONE_DEFAULT


class TestFormatInitialPlaceholder:
    """format_initial_placeholder 테스트"""

    def test_is_blockquote(self):
        result = format_initial_placeholder()
        assert result.startswith("> ")

    def test_contains_thinking_emoji(self):
        result = format_initial_placeholder()
        assert _emoji_thinking() in result

    def test_contains_placeholder_text(self):
        result = format_initial_placeholder()
        assert "*소영이 생각합니다...*" in result

    def test_custom_emoji_via_env(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_THINKING": ":ssy-thinking:"}):
            result = format_initial_placeholder()
            assert ":ssy-thinking:" in result


class TestFormatThinkingInitial:
    """format_thinking_initial 테스트"""

    def test_contains_emoji_and_bold(self):
        result = format_thinking_initial()
        assert _emoji_thinking() in result
        assert "*생각합니다...*" in result


class TestFormatThinkingText:
    """format_thinking_text 테스트 — blockquote 형식"""

    def test_contains_header_and_blockquote(self):
        result = format_thinking_text("I need to analyze this")
        assert "*생각합니다...*" in result
        assert "> I need to analyze this" in result
        # code block이 아닌 blockquote 형식
        assert "```" not in result

    def test_multiline_text_in_blockquote(self):
        result = format_thinking_text("line1\nline2\nline3")
        assert "> line1" in result
        assert "> line2" in result
        assert "> line3" in result

    def test_backticks_escaped(self):
        result = format_thinking_text("use `grep` command")
        assert "`" not in result
        assert "grep" in result

    def test_long_text_truncated_from_front(self):
        """긴 텍스트는 앞에서 잘려서 최신 내용이 표시된다"""
        long_text = "A" * 200 + "LATEST_CONTENT"
        padded = long_text + "B" * 500  # 총 길이 > THINKING_QUOTE_MAX_LEN
        result = format_thinking_text(padded)
        assert "..." in result
        # 뒤쪽 내용(B 반복)이 남아있어야 함
        assert "B" in result

    def test_truncation_preserves_tail(self):
        """truncation은 뒤쪽(최신)을 보존한다"""
        text = "OLD_" * 200 + "NEW_END"
        result = format_thinking_text(text)
        assert "NEW_END" in result

    def test_empty_text_returns_initial(self):
        result = format_thinking_text("")
        expected = format_thinking_initial()
        assert result == expected

    def test_whitespace_only_returns_initial(self):
        result = format_thinking_text("   \n  ")
        expected = format_thinking_initial()
        assert result == expected

    def test_none_text_returns_initial(self):
        result = format_thinking_text(None)
        expected = format_thinking_initial()
        assert result == expected


class TestFormatThinkingComplete:
    """format_thinking_complete 테스트"""

    def test_uses_done_emoji(self):
        result = format_thinking_complete("some thought")
        assert _emoji_thinking_done() in result
        assert _emoji_thinking() not in result or _emoji_thinking() == _emoji_thinking_done()

    def test_contains_text_in_blockquote(self):
        result = format_thinking_complete("final thought")
        assert "> final thought" in result
        assert "*생각합니다...*" in result

    def test_empty_text_header_only(self):
        result = format_thinking_complete("")
        assert _emoji_thinking_done() in result
        assert "*생각합니다...*" in result
        # 헤더 뒤에 blockquote가 없어야 한다
        parts = result.split("*생각합니다...*")
        assert len(parts) == 2
        assert ">" not in parts[1]

    def test_none_text_handled(self):
        result = format_thinking_complete(None)
        assert _emoji_thinking_done() in result
        assert "*생각합니다...*" in result

    def test_long_text_truncated(self):
        long_text = "x" * (THINKING_QUOTE_MAX_LEN + 200)
        result = format_thinking_complete(long_text)
        assert "..." in result

    def test_custom_done_emoji_via_env(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_THINKING_DONE": ":ssy-happy:"}):
            result = format_thinking_complete("done")
            assert ":ssy-happy:" in result


class TestFormatToolInputReadable:
    """_format_tool_input_readable 테스트"""

    def test_none_returns_empty(self):
        assert _format_tool_input_readable(None) == ""

    def test_dict_key_value_pairs(self):
        result = _format_tool_input_readable({"pattern": "*.py", "path": "/src"})
        assert "> *pattern*" in result
        assert "> *.py" in result
        assert "> *path*" in result
        assert "> /src" in result

    def test_dict_keys_are_bold(self):
        result = _format_tool_input_readable({"command": "ls -la"})
        assert "> *command*" in result

    def test_non_dict_as_single_quote(self):
        result = _format_tool_input_readable("simple value")
        assert result == "> simple value"

    def test_long_value_truncated(self):
        result = _format_tool_input_readable({"data": "x" * 500})
        assert "..." in result

    def test_long_string_input_truncated(self):
        result = _format_tool_input_readable("y" * 500)
        assert "..." in result
        assert len(result) <= TOOL_INPUT_QUOTE_MAX_LEN + 10  # "> " + "..." overhead

    def test_no_trailing_empty_quote(self):
        """마지막에 빈 > 줄이 없어야 한다"""
        result = _format_tool_input_readable({"a": "1", "b": "2"})
        assert not result.endswith(">")
        assert not result.endswith(">\n")

    def test_backticks_in_value_escaped(self):
        result = _format_tool_input_readable({"cmd": "echo `hi`"})
        assert "`" not in result
        assert "hi" in result


class TestFormatToolInitial:
    """format_tool_initial 테스트"""

    def test_header_only_without_input(self):
        result = format_tool_initial("Grep")
        assert _emoji_tool() in result
        assert "*Grep*" in result
        assert "\n>" not in result

    def test_header_and_readable_input(self):
        result = format_tool_initial("Grep", {"pattern": "hello", "path": "src/"})
        assert "*Grep*" in result
        assert "> *pattern*" in result
        assert "> hello" in result
        assert "> *path*" in result
        assert "> src/" in result

    def test_none_input_same_as_no_input(self):
        result_none = format_tool_initial("Read", None)
        result_no_arg = format_tool_initial("Read")
        assert result_none == result_no_arg

    def test_empty_dict_input_no_quote(self):
        """빈 dict는 falsy이므로 input 줄이 표시되지 않음"""
        result = format_tool_initial("Bash", {})
        assert "\n>" not in result

    def test_string_input(self):
        result = format_tool_initial("Bash", "ls -la")
        assert "*Bash*" in result
        assert "> ls -la" in result

    def test_custom_tool_emoji(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_TOOL": ":ssy-tool:"}):
            result = format_tool_initial("Read")
            assert ":ssy-tool:" in result


class TestFormatToolResult:
    """format_tool_result 테스트"""

    def test_success_with_string_result(self):
        result = format_tool_result("Grep", "3 matches found")
        assert _emoji_tool_done() in result
        assert "*Grep*" in result
        assert "> 3 matches found" in result

    def test_success_with_empty_result(self):
        result = format_tool_result("Grep", None)
        assert _emoji_tool_done() in result
        assert "*Grep*" in result

    def test_success_with_dict_result(self):
        result = format_tool_result("Read", {"lines": 42, "path": "foo.py"})
        assert _emoji_tool_done() in result
        assert "lines" in result
        assert "42" in result

    def test_success_with_list_result(self):
        result = format_tool_result("Glob", ["a.py", "b.py"])
        assert _emoji_tool_done() in result
        assert "a.py" in result

    def test_long_result_truncated(self):
        long_result = "x" * (TOOL_RESULT_MAX_LEN + 200)
        result = format_tool_result("Bash", long_result)
        assert "..." in result

    def test_error_format(self):
        result = format_tool_result("Bash", "command not found: xyz", is_error=True)
        assert ":x:" in result
        assert "*Bash*" in result
        assert "> command not found: xyz" in result
        # done 이모지가 아닌 :x:
        assert _emoji_tool_done() not in result or ":x:" in result

    def test_error_backticks_escaped(self):
        result = format_tool_result("Bash", "error in `main`", is_error=True)
        assert "`" not in result
        assert "main" in result

    def test_multiline_result_blockquoted(self):
        result = format_tool_result("Bash", "line1\nline2\nline3")
        assert "> line1" in result
        assert "> line2" in result
        assert "> line3" in result

    def test_success_with_empty_string_result(self):
        """빈 문자열 결과는 blockquote 없이 헤더만"""
        result = format_tool_result("Grep", "")
        assert _emoji_tool_done() in result
        assert "*Grep*" in result
        assert ">" not in result

    def test_non_serializable_result(self):
        """json.dumps 실패 시 str() fallback"""
        result = format_tool_result("Test", {"fn": lambda: None})
        assert "*Test*" in result

    def test_error_long_result_truncated(self):
        """에러 결과도 truncation + ... 표시"""
        long_error = "E" * (TOOL_RESULT_MAX_LEN + 200)
        result = format_tool_result("Bash", long_error, is_error=True)
        assert "..." in result

    def test_error_multiline_blockquoted(self):
        """멀티라인 에러도 모든 줄이 blockquote"""
        result = format_tool_result("Bash", "error1\nerror2", is_error=True)
        assert "> error1" in result
        assert "> error2" in result


class TestFormatToolComplete:
    """format_tool_complete 테스트"""

    def test_uses_done_emoji(self):
        result = format_tool_complete("Grep")
        assert _emoji_tool_done() in result
        assert "*Grep*" in result

    def test_no_done_text(self):
        """이전의 (done) 텍스트가 없어야 한다"""
        result = format_tool_complete("Grep")
        assert "(done)" not in result

    def test_custom_done_emoji(self):
        with patch.dict(os.environ, {"SOULSTREAM_EMOJI_TOOL_DONE": ":ssy-done:"}):
            result = format_tool_complete("Read")
            assert ":ssy-done:" in result


class TestNormalizeNewlines:
    """_normalize_newlines 테스트"""

    def test_no_change_for_single_newline(self):
        assert _normalize_newlines("a\nb") == "a\nb"

    def test_no_change_for_double_newline(self):
        assert _normalize_newlines("a\n\nb") == "a\n\nb"

    def test_triple_newline_reduced_to_double(self):
        assert _normalize_newlines("a\n\n\nb") == "a\n\nb"

    def test_many_newlines_reduced(self):
        assert _normalize_newlines("a\n\n\n\n\n\nb") == "a\n\nb"

    def test_multiple_groups_normalized(self):
        result = _normalize_newlines("a\n\n\nb\n\n\n\nc")
        assert result == "a\n\nb\n\nc"

    def test_empty_string(self):
        assert _normalize_newlines("") == ""

    def test_no_newlines(self):
        assert _normalize_newlines("hello world") == "hello world"


class TestQuoteLinesNewlineNormalization:
    """_quote_lines의 줄바꿈 정규화 통합 테스트"""

    def test_consecutive_blank_lines_normalized_in_blockquote(self):
        """연속 빈 줄이 단일 빈 줄로 정규화된 후 blockquote 처리됨"""
        result = _quote_lines("line1\n\n\n\nline2")
        assert result == "> line1\n> \n> line2"

    def test_single_blank_line_preserved(self):
        """단일 빈 줄은 유지됨"""
        result = _quote_lines("para1\n\npara2")
        assert result == "> para1\n> \n> para2"

    def test_all_lines_have_prefix(self):
        """모든 줄에 > prefix가 붙음"""
        result = _quote_lines("a\nb\nc")
        for line in result.split("\n"):
            assert line.startswith("> ")


class TestMultilineToolInputBlockquote:
    """에이전트(Task) 호출 시 멀티라인 tool_input blockquote 이탈 방지 테스트"""

    def test_multiline_value_all_lines_quoted(self):
        """dict value에 줄바꿈이 포함되면 모든 줄에 > prefix 적용"""
        result = _format_tool_input_readable({"prompt": "line1\nline2\nline3"})
        for line in result.split("\n"):
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"

    def test_multiline_value_with_blank_lines(self):
        """빈 줄 포함된 value도 모든 줄이 blockquote 안에 있음"""
        result = _format_tool_input_readable({"prompt": "step1\n\nstep2"})
        for line in result.split("\n"):
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"

    def test_consecutive_newlines_normalized(self):
        """연속 줄바꿈이 정규화되어 3줄 이상의 빈 blockquote가 없음"""
        result = _format_tool_input_readable({"prompt": "a\n\n\n\nb"})
        # 연속 빈 > 줄이 2개 이상 나오면 안됨
        lines = result.split("\n")
        consecutive_empty = 0
        for line in lines:
            if line.strip() == ">":
                consecutive_empty += 1
                assert consecutive_empty <= 1, "연속 빈 blockquote 줄이 2개 이상"
            else:
                consecutive_empty = 0

    def test_non_dict_multiline_all_quoted(self):
        """non-dict 멀티라인 입력도 모든 줄에 > prefix 적용"""
        result = _format_tool_input_readable("line1\nline2\nline3")
        for line in result.split("\n"):
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"

    def test_format_tool_initial_multiline_prompt(self):
        """format_tool_initial에서 멀티라인 prompt가 blockquote에서 이탈하지 않음"""
        result = format_tool_initial("Task", {"prompt": "step1\nstep2\nstep3"})
        lines = result.split("\n")
        # 첫 줄은 헤더 (> 없음), 나머지는 모두 blockquote
        for line in lines[1:]:
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"

    def test_tool_result_multiline_all_quoted(self):
        """format_tool_result에서 멀티라인 결과도 모든 줄이 blockquote"""
        result = format_tool_result("Bash", "output1\noutput2\n\noutput3")
        lines = result.split("\n")
        for line in lines[1:]:
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"

    def test_thinking_text_multiline_all_quoted(self):
        """format_thinking_text에서 멀티라인 thinking도 모든 줄이 blockquote"""
        result = format_thinking_text("thought1\n\nthought2\nthought3")
        lines = result.split("\n")
        for line in lines[1:]:  # 첫 줄은 헤더
            assert line.startswith(">"), f"blockquote 이탈: {line!r}"


