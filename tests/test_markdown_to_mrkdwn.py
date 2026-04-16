"""markdown_to_mrkdwn 변환 함수 유닛 테스트

Markdown → Slack mrkdwn 변환을 검증합니다.
"""

from seosoyoung.slackbot.formatting import markdown_to_mrkdwn


class TestBold:
    """Markdown 굵게 → Slack 굵게"""

    def test_double_asterisk(self):
        assert markdown_to_mrkdwn("hello **world**") == "hello *world*"

    def test_double_underscore(self):
        assert markdown_to_mrkdwn("hello __world__") == "hello *world*"

    def test_multiple_bold(self):
        result = markdown_to_mrkdwn("**a** and **b**")
        assert result == "*a* and *b*"


class TestItalic:
    """Markdown 기울임 → Slack 기울임"""

    def test_single_underscore(self):
        """Markdown _text_ → Slack _text_ (동일)"""
        assert markdown_to_mrkdwn("hello _world_") == "hello _world_"

    def test_single_asterisk_italic(self):
        """Markdown *text* 기울임은 Slack에서 굵게와 충돌하므로 그대로 둔다"""
        # Markdown *text* 는 Slack에서는 이미 *굵게*와 같은 표기
        # 이중 변환 방지를 위해 그대로 둔다
        result = markdown_to_mrkdwn("hello *world*")
        assert result == "hello *world*"


class TestLinks:
    """Markdown 링크 → Slack 링크"""

    def test_basic_link(self):
        result = markdown_to_mrkdwn("[구글](https://google.com)")
        assert result == "<https://google.com|구글>"

    def test_multiple_links(self):
        result = markdown_to_mrkdwn("[a](http://a.com) and [b](http://b.com)")
        assert result == "<http://a.com|a> and <http://b.com|b>"

    def test_link_with_special_chars(self):
        result = markdown_to_mrkdwn("[이슈 #42](https://github.com/org/repo/issues/42)")
        assert result == "<https://github.com/org/repo/issues/42|이슈 #42>"


class TestStrikethrough:
    """Markdown 취소선 → Slack 취소선"""

    def test_double_tilde(self):
        assert markdown_to_mrkdwn("~~deleted~~") == "~deleted~"

    def test_multiple_strikethrough(self):
        result = markdown_to_mrkdwn("~~a~~ and ~~b~~")
        assert result == "~a~ and ~b~"


class TestHeadings:
    """Markdown 제목 → Slack 굵게"""

    def test_h1(self):
        assert markdown_to_mrkdwn("# Title") == "*Title*"

    def test_h2(self):
        assert markdown_to_mrkdwn("## Subtitle") == "*Subtitle*"

    def test_h3(self):
        assert markdown_to_mrkdwn("### Section") == "*Section*"

    def test_heading_only_at_line_start(self):
        """줄 중간의 #은 변환하지 않음"""
        result = markdown_to_mrkdwn("issue #42 is important")
        assert result == "issue #42 is important"

    def test_multiline_heading(self):
        result = markdown_to_mrkdwn("# Title\nsome text\n## Subtitle")
        assert result == "*Title*\nsome text\n*Subtitle*"


class TestCodePreservation:
    """코드블록과 인라인코드 보존"""

    def test_inline_code_preserved(self):
        result = markdown_to_mrkdwn("use `**bold**` syntax")
        assert "`**bold**`" in result

    def test_code_block_preserved(self):
        text = "before\n```python\n**not bold**\n```\nafter"
        result = markdown_to_mrkdwn(text)
        assert "```python\n**not bold**\n```" in result

    def test_code_block_with_markdown_inside(self):
        text = "```\n# not a heading\n[not](a link)\n```"
        result = markdown_to_mrkdwn(text)
        assert "# not a heading" in result
        assert "[not](a link)" in result


class TestBlockquotePreservation:
    """blockquote 보존"""

    def test_blockquote_preserved(self):
        result = markdown_to_mrkdwn("> this is a quote")
        assert result == "> this is a quote"

    def test_blockquote_with_bold_inside(self):
        """blockquote 내부의 마크다운도 보존"""
        result = markdown_to_mrkdwn("> **bold** in quote")
        assert result == "> **bold** in quote"

    def test_multiline_blockquote(self):
        text = "> line 1\n> line 2\n> line 3"
        result = markdown_to_mrkdwn(text)
        assert result == "> line 1\n> line 2\n> line 3"

    def test_mixed_blockquote_and_normal(self):
        text = "normal text\n> quoted text\nmore normal"
        result = markdown_to_mrkdwn(text)
        assert "> quoted text" in result
        # normal text 부분만 변환되어야 함


class TestTable:
    """Markdown 표 → 텍스트 변환"""

    def test_simple_table(self):
        table = "| Name | Value |\n|------|-------|\n| a | 1 |\n| b | 2 |"
        result = markdown_to_mrkdwn(table)
        # 파이프와 정렬 행이 제거되고 텍스트로 변환
        assert "---" not in result
        assert "Name" in result
        assert "a" in result

    def test_table_separator_row_removed(self):
        """정렬 행(|---|---|)이 제거됨"""
        table = "| H1 | H2 |\n|---|---|\n| a | b |"
        result = markdown_to_mrkdwn(table)
        assert "---|---" not in result


class TestHorizontalRule:
    """수평선 제거"""

    def test_triple_dash(self):
        result = markdown_to_mrkdwn("above\n---\nbelow")
        assert "---" not in result
        assert "above" in result
        assert "below" in result

    def test_triple_asterisk(self):
        result = markdown_to_mrkdwn("above\n***\nbelow")
        assert "***" not in result

    def test_triple_underscore(self):
        result = markdown_to_mrkdwn("above\n___\nbelow")
        assert "___" not in result


class TestConsecutiveNewlines:
    """연속 빈 줄 정리"""

    def test_triple_newlines_reduced(self):
        result = markdown_to_mrkdwn("a\n\n\nb")
        assert result == "a\n\nb"

    def test_many_newlines_reduced(self):
        result = markdown_to_mrkdwn("a\n\n\n\n\nb")
        assert result == "a\n\nb"


class TestSlackLinkPreservation:
    """기존 Slack mrkdwn 링크 보존"""

    def test_slack_link_not_modified(self):
        text = "check <https://example.com|this link>"
        result = markdown_to_mrkdwn(text)
        assert "<https://example.com|this link>" in result


class TestComplexCases:
    """복합 케이스"""

    def test_bold_and_link(self):
        result = markdown_to_mrkdwn("**important** [link](http://x.com)")
        assert "*important*" in result
        assert "<http://x.com|link>" in result

    def test_heading_with_bold(self):
        result = markdown_to_mrkdwn("## **Title**")
        # 제목 변환 후 내부 ** 도 변환
        assert "*" in result
        assert "Title" in result

    def test_empty_string(self):
        assert markdown_to_mrkdwn("") == ""

    def test_no_markdown(self):
        text = "just plain text"
        assert markdown_to_mrkdwn(text) == text

    def test_real_world_claude_response(self):
        """실제 Claude 응답 형태의 변환"""
        text = (
            "## 요약\n\n"
            "**3줄 요약:**\n"
            "- 첫 번째 항목\n"
            "- 두 번째 항목\n"
            "- 세 번째 항목\n\n"
            "자세한 내용은 [문서](https://docs.example.com)를 참조하세요.\n\n"
            "```python\ndef hello():\n    print('world')\n```\n\n"
            "> 인용문입니다"
        )
        result = markdown_to_mrkdwn(text)
        # 제목 변환
        assert "*요약*" in result
        # 굵게 변환
        assert "*3줄 요약:*" in result
        # 링크 변환
        assert "<https://docs.example.com|문서>" in result
        # 코드블록 보존
        assert "```python" in result
        assert "def hello():" in result
        # blockquote 보존
        assert "> 인용문입니다" in result
