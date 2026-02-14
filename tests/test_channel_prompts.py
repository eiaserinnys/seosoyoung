"""채널 프롬프트 포맷 함수 테스트

reactions 필드가 있는 메시지의 포맷팅을 검증합니다.
"""

from seosoyoung.memory.channel_prompts import (
    _format_channel_messages,
    _format_pending_messages,
    _format_thread_messages,
)


class TestFormatPendingMessagesReactions:
    """pending 메시지 포맷에 reactions 표시"""

    def test_message_without_reactions(self):
        """reactions가 없는 메시지는 기존 포맷 유지"""
        msgs = [{"ts": "1.1", "user": "U001", "text": "hello"}]
        result = _format_pending_messages(msgs)
        assert result == "[1.1] <U001>: hello"

    def test_message_with_single_reaction(self):
        """reactions가 하나인 메시지"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [{"name": "thumbsup", "users": ["U002"], "count": 1}],
        }]
        result = _format_pending_messages(msgs)
        assert ":thumbsup:×1" in result

    def test_message_with_multiple_reactions(self):
        """reactions가 여러 개인 메시지"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [
                {"name": "thumbsup", "users": ["U002", "U003"], "count": 2},
                {"name": "heart", "users": ["U004"], "count": 1},
            ],
        }]
        result = _format_pending_messages(msgs)
        assert ":thumbsup:×2" in result
        assert ":heart:×1" in result

    def test_empty_reactions_list(self):
        """reactions가 빈 리스트인 경우"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [],
        }]
        result = _format_pending_messages(msgs)
        # 빈 리스트면 reactions 표시 없음
        assert "×" not in result


class TestFormatChannelMessagesReactions:
    """채널 메시지 포맷에 reactions 표시"""

    def test_message_with_reactions(self):
        """채널 메시지에도 reactions 표시"""
        msgs = [{
            "ts": "1.1", "user": "U001", "text": "hello",
            "reactions": [{"name": "fire", "users": ["U002", "U003"], "count": 2}],
        }]
        result = _format_channel_messages(msgs)
        assert ":fire:×2" in result


class TestFormatThreadMessagesReactions:
    """스레드 메시지 포맷에 reactions 표시"""

    def test_thread_message_with_reactions(self):
        """스레드 메시지에도 reactions 표시"""
        buffers = {
            "parent.ts": [{
                "ts": "2.1", "user": "U001", "text": "reply",
                "reactions": [{"name": "eyes", "users": ["U002"], "count": 1}],
            }],
        }
        result = _format_thread_messages(buffers)
        assert ":eyes:×1" in result
