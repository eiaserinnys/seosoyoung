"""slack/formatting.py 유틸리티 테스트"""

import pytest
from unittest.mock import MagicMock

from seosoyoung.slackbot.slack.formatting import update_message, build_section_blocks


class TestBuildSectionBlocks:
    """build_section_blocks 함수 테스트"""

    def test_basic_text(self):
        """기본 텍스트로 mrkdwn section block 생성"""
        blocks = build_section_blocks("hello")
        assert blocks == [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": "hello"}
        }]

    def test_multiline_text(self):
        """여러 줄 텍스트"""
        text = "line1\nline2\nline3"
        blocks = build_section_blocks(text)
        assert blocks[0]["text"]["text"] == text


class TestUpdateMessage:
    """update_message 함수 테스트"""

    def test_basic_update(self):
        """기본 chat_update 호출"""
        client = MagicMock()
        update_message(client, "C123", "1234.5678", "hello world")

        client.chat_update.assert_called_once_with(
            channel="C123",
            ts="1234.5678",
            text="hello world",
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "hello world"}
            }],
        )

    def test_custom_blocks(self):
        """커스텀 blocks를 전달하면 그대로 사용"""
        client = MagicMock()
        custom_blocks = [{"type": "divider"}]
        update_message(client, "C123", "1234.5678", "hello", blocks=custom_blocks)

        client.chat_update.assert_called_once_with(
            channel="C123",
            ts="1234.5678",
            text="hello",
            blocks=custom_blocks,
        )

    def test_returns_none_by_default(self):
        """기본적으로 None 반환"""
        client = MagicMock()
        result = update_message(client, "C123", "1234.5678", "hello")
        assert result is None
