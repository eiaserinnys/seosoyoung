"""format_slack_message() 헬퍼 단위 테스트

슬랙 메시지를 프롬프트 주입용 텍스트로 포맷하는 헬퍼의 동작을 검증합니다.
"""

import pytest

from seosoyoung.slackbot.slack.message_formatter import format_slack_message


class TestBasicFormatting:
    """기본 텍스트 메시지 포맷팅"""

    def test_simple_message(self):
        """일반 텍스트 메시지"""
        msg = {"user": "U123", "text": "Hello world", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "[C001:1234.5678]" in result
        assert "<U123>:" in result
        assert "Hello world" in result

    def test_no_channel(self):
        """채널 없이 ts만 있는 경우"""
        msg = {"user": "U123", "text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg)
        assert "[ts:1234.5678]" in result
        assert "<U123>:" in result

    def test_no_meta(self):
        """include_meta=False면 메타데이터 프리픽스 없음"""
        msg = {"user": "U123", "text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001", include_meta=False)
        assert "[C001:" not in result
        assert "[ts:" not in result
        assert "<U123>: Hello" in result

    def test_empty_text(self):
        """텍스트가 비어있는 메시지"""
        msg = {"user": "U123", "text": "", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "<U123>:" in result

    def test_missing_user(self):
        """user 필드가 없는 메시지"""
        msg = {"text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "<unknown>:" in result

    def test_missing_ts(self):
        """ts 필드가 없는 메시지"""
        msg = {"user": "U123", "text": "Hello"}
        result = format_slack_message(msg, channel="C001")
        # ts가 없으면 메타데이터 생략
        assert "[C001:" not in result
        assert "<U123>: Hello" in result


class TestRichTextBlocks:
    """Block Kit 리치 텍스트 파싱"""

    def test_preformatted_block(self):
        """코드블록/표 (rich_text_preformatted)"""
        msg = {
            "user": "U123",
            "text": "코드입니다",
            "ts": "1234.5678",
            "blocks": [{
                "type": "rich_text",
                "elements": [{
                    "type": "rich_text_preformatted",
                    "elements": [
                        {"type": "text", "text": "def hello():\n    print('hi')"}
                    ]
                }]
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "```" in result
        assert "def hello():" in result

    def test_ordered_list(self):
        """순서 목록 (rich_text_list, ordered)"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "blocks": [{
                "type": "rich_text",
                "elements": [{
                    "type": "rich_text_list",
                    "style": "ordered",
                    "elements": [
                        {"type": "rich_text_section", "elements": [{"type": "text", "text": "첫 번째"}]},
                        {"type": "rich_text_section", "elements": [{"type": "text", "text": "두 번째"}]},
                    ]
                }]
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "1." in result
        assert "2." in result
        assert "첫 번째" in result
        assert "두 번째" in result

    def test_bullet_list(self):
        """비순서 목록 (rich_text_list, bullet)"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "blocks": [{
                "type": "rich_text",
                "elements": [{
                    "type": "rich_text_list",
                    "style": "bullet",
                    "elements": [
                        {"type": "rich_text_section", "elements": [{"type": "text", "text": "항목 A"}]},
                    ]
                }]
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "- 항목 A" in result

    def test_quote_block(self):
        """인용 (rich_text_quote)"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "blocks": [{
                "type": "rich_text",
                "elements": [{
                    "type": "rich_text_quote",
                    "elements": [{"type": "text", "text": "인용문입니다"}]
                }]
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "> 인용문입니다" in result

    def test_non_rich_text_block_ignored(self):
        """rich_text가 아닌 블록은 무시"""
        msg = {
            "user": "U123",
            "text": "Hello",
            "ts": "1234.5678",
            "blocks": [{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "ignored"}
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "ignored" not in result
        assert "Hello" in result


class TestFileAttachments:
    """첨부 파일 포맷팅"""

    def test_single_file(self):
        """파일 1개 첨부"""
        msg = {
            "user": "U123",
            "text": "파일 보내요",
            "ts": "1234.5678",
            "files": [{
                "name": "report.pdf",
                "mimetype": "application/pdf",
                "size": 1024,
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "[첨부: report.pdf" in result
        assert "application/pdf" in result
        assert "1024B" in result

    def test_multiple_files(self):
        """파일 여러 개 첨부"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "files": [
                {"name": "image.png", "mimetype": "image/png", "size": 2048},
                {"name": "doc.txt", "mimetype": "text/plain", "size": 512},
            ]
        }
        result = format_slack_message(msg, channel="C001")
        assert "image.png" in result
        assert "doc.txt" in result


class TestAttachments:
    """Attachments (unfurl, 봇 카드) 포맷팅"""

    def test_unfurl_with_title(self):
        """링크 unfurl (title이 있는 경우)"""
        msg = {
            "user": "U123",
            "text": "https://example.com",
            "ts": "1234.5678",
            "attachments": [{
                "title": "Example Page",
                "text": "This is an example",
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "[링크: Example Page]" in result

    def test_attachment_with_fields(self):
        """attachment fields (key-value 데이터)"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "attachments": [{
                "title": "Deploy Status",
                "fields": [
                    {"title": "Environment", "value": "production"},
                    {"title": "Status", "value": "success"},
                ]
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "Environment: production" in result
        assert "Status: success" in result

    def test_bot_message_attachment(self):
        """봇 메시지 attachment (title 없고 text만 있는 경우)"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "attachments": [{
                "text": "Bot notification content",
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "[봇 메시지:" in result
        assert "Bot notification content" in result

    def test_attachment_fallback(self):
        """fallback 텍스트 사용"""
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "attachments": [{
                "fallback": "Fallback Title",
            }]
        }
        result = format_slack_message(msg, channel="C001")
        assert "[링크: Fallback Title]" in result


class TestReactions:
    """리액션 포맷팅"""

    def test_single_reaction(self):
        """리액션 1개"""
        msg = {
            "user": "U123",
            "text": "Good idea",
            "ts": "1234.5678",
            "reactions": [
                {"name": "thumbsup", "count": 3}
            ]
        }
        result = format_slack_message(msg, channel="C001")
        assert "[리액션:" in result
        assert ":thumbsup: x3" in result

    def test_multiple_reactions(self):
        """리액션 여러 개"""
        msg = {
            "user": "U123",
            "text": "Announcement",
            "ts": "1234.5678",
            "reactions": [
                {"name": "heart", "count": 5},
                {"name": "rocket", "count": 2},
            ]
        }
        result = format_slack_message(msg, channel="C001")
        assert ":heart: x5" in result
        assert ":rocket: x2" in result

    def test_no_reactions(self):
        """리액션이 없는 경우 [리액션:] 미출력"""
        msg = {"user": "U123", "text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "[리액션:" not in result


class TestBotMessages:
    """봇 메시지 구분"""

    def test_bot_message_with_profile(self):
        """bot_id가 있고 bot_profile이 있는 경우"""
        msg = {
            "user": "U_BOT",
            "text": "Bot says hello",
            "ts": "1234.5678",
            "bot_id": "B123",
            "bot_profile": {"name": "MyBot"}
        }
        result = format_slack_message(msg, channel="C001")
        assert "<bot:MyBot>:" in result
        assert "<U_BOT>:" not in result

    def test_bot_message_without_profile(self):
        """bot_id만 있고 bot_profile이 없는 경우"""
        msg = {
            "user": "U_BOT",
            "text": "Bot says hello",
            "ts": "1234.5678",
            "bot_id": "B123",
        }
        result = format_slack_message(msg, channel="C001")
        assert "<bot:B123>:" in result

    def test_regular_user_not_marked_as_bot(self):
        """일반 사용자 메시지는 봇으로 표시되지 않음"""
        msg = {"user": "U123", "text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "<U123>:" in result
        assert "<bot:" not in result


class TestLinkedMessages:
    """linked_message_ts 처리 (hybrid 세션용)"""

    def test_linked_message(self):
        """linked_message_ts가 있는 메시지"""
        msg = {
            "user": "U123",
            "text": "답변입니다",
            "ts": "1234.5678",
            "linked_message_ts": "1234.0000",
        }
        result = format_slack_message(msg, channel="C001")
        assert "[linked:1234.0000]" in result

    def test_no_linked_message(self):
        """linked_message_ts가 없는 메시지"""
        msg = {"user": "U123", "text": "Hello", "ts": "1234.5678"}
        result = format_slack_message(msg, channel="C001")
        assert "[linked:" not in result


class TestEdgeCases:
    """엣지 케이스"""

    def test_empty_message(self):
        """완전히 빈 메시지 dict"""
        result = format_slack_message({})
        assert "<unknown>:" in result

    def test_complex_message(self):
        """여러 요소가 복합된 메시지"""
        msg = {
            "user": "U123",
            "text": "복합 메시지",
            "ts": "1234.5678",
            "blocks": [{
                "type": "rich_text",
                "elements": [{
                    "type": "rich_text_quote",
                    "elements": [{"type": "text", "text": "인용"}]
                }]
            }],
            "files": [{"name": "img.png", "mimetype": "image/png", "size": 100}],
            "reactions": [{"name": "fire", "count": 1}],
        }
        result = format_slack_message(msg, channel="C001")
        assert "[C001:1234.5678]" in result
        assert "복합 메시지" in result
        assert "> 인용" in result
        assert "[첨부: img.png" in result
        assert ":fire: x1" in result

    def test_long_bot_attachment_text_truncated(self):
        """봇 attachment text가 200자로 잘림"""
        long_text = "A" * 300
        msg = {
            "user": "U123",
            "text": "",
            "ts": "1234.5678",
            "attachments": [{"text": long_text}],
        }
        result = format_slack_message(msg, channel="C001")
        # 200자까지만 포함
        assert "A" * 200 in result
        assert "A" * 201 not in result
