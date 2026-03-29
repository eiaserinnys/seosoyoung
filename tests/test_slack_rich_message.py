"""SlackBackendImpl rich field 파싱 단위 테스트.

Message dataclass의 reactions/files/blocks 필드 파싱 동작을 검증합니다.
"""

from unittest.mock import MagicMock

import pytest

from seosoyoung.plugin_sdk.slack import FileInfo, Message, Reaction
from seosoyoung.slackbot.plugin_backends import (
    SlackBackendImpl,
    _parse_files,
    _parse_reactions,
)


# ============================================================================
# 헬퍼 함수 단위 테스트
# ============================================================================


class TestParseReactions:
    """_parse_reactions 헬퍼 함수 테스트"""

    def test_parses_reactions_with_users(self):
        """reactions 필드를 Reaction 목록으로 올바르게 변환"""
        raw = [
            {"name": "thumbsup", "count": 3, "users": ["U1", "U2", "U3"]},
            {"name": "tada", "count": 1, "users": ["U4"]},
        ]
        result = _parse_reactions(raw)

        assert len(result) == 2
        assert result[0] == Reaction(name="thumbsup", count=3, users=["U1", "U2", "U3"])
        assert result[1] == Reaction(name="tada", count=1, users=["U4"])

    def test_parses_reactions_without_users_field(self):
        """users 필드가 없으면 빈 리스트로 폴백"""
        raw = [{"name": "fire", "count": 2}]
        result = _parse_reactions(raw)

        assert len(result) == 1
        assert result[0].name == "fire"
        assert result[0].count == 2
        assert result[0].users == []

    def test_empty_raw_returns_empty_list(self):
        """빈 목록 입력 시 빈 목록 반환"""
        assert _parse_reactions([]) == []


class TestParseFiles:
    """_parse_files 헬퍼 함수 테스트"""

    def test_parses_files_with_all_fields(self):
        """files 필드를 FileInfo 목록으로 올바르게 변환"""
        raw = [
            {
                "name": "report.pdf",
                "title": "Q4 Report",
                "mimetype": "application/pdf",
                "permalink": "https://slack.com/files/U1/F1/report.pdf",
            }
        ]
        result = _parse_files(raw)

        assert len(result) == 1
        assert result[0] == FileInfo(
            name="report.pdf",
            title="Q4 Report",
            mimetype="application/pdf",
            permalink="https://slack.com/files/U1/F1/report.pdf",
        )

    def test_parses_files_with_missing_optional_fields(self):
        """일부 필드가 없으면 빈 문자열로 폴백"""
        raw = [{"mimetype": "image/png"}]
        result = _parse_files(raw)

        assert len(result) == 1
        assert result[0].name == ""
        assert result[0].title == ""
        assert result[0].mimetype == "image/png"
        assert result[0].permalink == ""

    def test_empty_raw_returns_empty_list(self):
        """빈 목록 입력 시 빈 목록 반환"""
        assert _parse_files([]) == []


# ============================================================================
# SlackBackendImpl.get_channel_history 테스트
# ============================================================================


def _make_client_with_history(messages: list[dict]) -> MagicMock:
    """conversations_history를 stub하는 클라이언트 생성 헬퍼."""
    client = MagicMock()
    client.conversations_history.return_value = {"messages": messages}
    return client


def _make_client_with_replies(messages: list[dict]) -> MagicMock:
    """conversations_replies를 stub하는 클라이언트 생성 헬퍼."""
    client = MagicMock()
    client.conversations_replies.return_value = {"messages": messages}
    return client


class TestGetChannelHistoryRichFields:
    """get_channel_history rich 필드 파싱 테스트"""

    @pytest.mark.asyncio
    async def test_parses_reactions_and_files_in_history(self):
        """reactions, files, blocks가 있는 메시지를 올바르게 파싱"""
        raw_msg = {
            "ts": "1234567890.000001",
            "text": "hello",
            "user": "U1",
            "reactions": [{"name": "thumbsup", "count": 1, "users": ["U2"]}],
            "files": [
                {
                    "name": "photo.png",
                    "title": "Photo",
                    "mimetype": "image/png",
                    "permalink": "https://slack.com/files/U1/F1/photo.png",
                }
            ],
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}],
        }
        client = _make_client_with_history([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_channel_history("C123")

        assert len(messages) == 1
        msg = messages[0]
        assert msg.ts == "1234567890.000001"
        assert msg.reactions == [Reaction(name="thumbsup", count=1, users=["U2"])]
        assert msg.files == [
            FileInfo(
                name="photo.png",
                title="Photo",
                mimetype="image/png",
                permalink="https://slack.com/files/U1/F1/photo.png",
            )
        ]
        assert len(msg.blocks) == 1
        assert msg.blocks[0]["type"] == "section"

    @pytest.mark.asyncio
    async def test_message_without_rich_fields_uses_empty_defaults(self):
        """reactions/files/blocks 없는 메시지는 빈 리스트로 처리"""
        raw_msg = {
            "ts": "1234567890.000002",
            "text": "plain message",
            "user": "U1",
        }
        client = _make_client_with_history([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_channel_history("C123")

        assert len(messages) == 1
        msg = messages[0]
        assert msg.reactions == []
        assert msg.files == []
        assert msg.blocks == []

    @pytest.mark.asyncio
    async def test_existing_fields_still_work(self):
        """기존 필드(ts, text, user, thread_ts, channel)가 정상 동작"""
        raw_msg = {
            "ts": "1111.0001",
            "text": "check",
            "user": "U99",
            "thread_ts": "1111.0000",
        }
        client = _make_client_with_history([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_channel_history("C_CHAN")

        assert messages[0].ts == "1111.0001"
        assert messages[0].text == "check"
        assert messages[0].user == "U99"
        assert messages[0].thread_ts == "1111.0000"
        assert messages[0].channel == "C_CHAN"

    @pytest.mark.asyncio
    async def test_multiple_messages_parsed_independently(self):
        """여러 메시지가 각각 독립적으로 파싱됨"""
        raw_msgs = [
            {"ts": "t1", "text": "msg1", "reactions": [{"name": "heart", "count": 1}]},
            {"ts": "t2", "text": "msg2"},
        ]
        client = _make_client_with_history(raw_msgs)
        backend = SlackBackendImpl(client)

        messages = await backend.get_channel_history("C123")

        assert len(messages) == 2
        assert len(messages[0].reactions) == 1
        assert len(messages[1].reactions) == 0


# ============================================================================
# SlackBackendImpl.get_thread_replies 테스트
# ============================================================================


class TestGetThreadRepliesRichFields:
    """get_thread_replies rich 필드 파싱 테스트"""

    @pytest.mark.asyncio
    async def test_parses_reactions_in_reply(self):
        """스레드 답글에서 reactions 파싱"""
        raw_msg = {
            "ts": "1234567890.000010",
            "text": "reply",
            "user": "U2",
            "reactions": [{"name": "eyes", "count": 2, "users": ["U3", "U4"]}],
        }
        client = _make_client_with_replies([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_thread_replies("C123", "1234567890.000000")

        assert len(messages) == 1
        assert messages[0].reactions == [
            Reaction(name="eyes", count=2, users=["U3", "U4"])
        ]

    @pytest.mark.asyncio
    async def test_reply_without_rich_fields_uses_empty_defaults(self):
        """rich 필드 없는 답글은 빈 리스트로 처리"""
        raw_msg = {"ts": "t1", "text": "simple reply", "user": "U1"}
        client = _make_client_with_replies([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_thread_replies("C123", "ts_parent")

        assert messages[0].reactions == []
        assert messages[0].files == []
        assert messages[0].blocks == []

    @pytest.mark.asyncio
    async def test_parses_files_in_reply(self):
        """스레드 답글에서 files 파싱"""
        raw_msg = {
            "ts": "t1",
            "text": "see file",
            "user": "U1",
            "files": [
                {
                    "name": "doc.txt",
                    "title": "Document",
                    "mimetype": "text/plain",
                    "permalink": "https://slack.com/files/U1/F2/doc.txt",
                }
            ],
        }
        client = _make_client_with_replies([raw_msg])
        backend = SlackBackendImpl(client)

        messages = await backend.get_thread_replies("C123", "ts_parent")

        assert len(messages[0].files) == 1
        assert messages[0].files[0].name == "doc.txt"


# ============================================================================
# Message dataclass 기본 동작 테스트
# ============================================================================


class TestMessageDataclass:
    """Message dataclass 기본 동작 테스트"""

    def test_default_rich_fields_are_empty_lists(self):
        """rich 필드 기본값이 빈 리스트 (공유 객체 아님)"""
        msg1 = Message(ts="t1", text="hello")
        msg2 = Message(ts="t2", text="world")

        # 각 인스턴스의 리스트가 독립적으로 생성됨
        msg1.reactions.append(Reaction(name="fire", count=1))
        assert msg2.reactions == [], "다른 인스턴스의 reactions가 공유되면 안 됨"

    def test_existing_fields_unchanged(self):
        """기존 필드가 변경 없이 동작"""
        msg = Message(ts="ts123", text="hi", user="U1", thread_ts="ts000", channel="C1")
        assert msg.ts == "ts123"
        assert msg.text == "hi"
        assert msg.user == "U1"
        assert msg.thread_ts == "ts000"
        assert msg.channel == "C1"
