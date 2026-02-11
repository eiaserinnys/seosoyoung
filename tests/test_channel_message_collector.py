"""채널 메시지 수집 통합 테스트

message handler가 관찰 대상 채널의 메시지를 ChannelStore에 저장하는지 검증합니다.
"""

from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.memory.channel_store import ChannelStore


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


@pytest.fixture
def collector(store):
    from seosoyoung.handlers.channel_collector import ChannelMessageCollector
    return ChannelMessageCollector(store=store, target_channels=["C_OBSERVE"])


class TestChannelMessageCollector:
    """채널 메시지 수집기 테스트"""

    def test_collect_channel_root_message(self, collector, store):
        """채널 루트 메시지(thread_ts 없음)를 수집"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "안녕하세요!",
        }
        collector.collect(event)

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["ts"] == "1234.5678"
        assert messages[0]["user"] == "U001"
        assert messages[0]["text"] == "안녕하세요!"

    def test_collect_thread_message(self, collector, store):
        """스레드 메시지(thread_ts 있음)를 수집"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.9999",
            "user": "U001",
            "text": "스레드 답글",
            "thread_ts": "1234.5678",
        }
        collector.collect(event)

        messages = store.load_thread_buffer("C_OBSERVE", "1234.5678")
        assert len(messages) == 1
        assert messages[0]["text"] == "스레드 답글"
        assert messages[0]["thread_ts"] == "1234.5678"

    def test_ignore_non_target_channel(self, collector, store):
        """관찰 대상이 아닌 채널은 무시"""
        event = {
            "channel": "C_OTHER",
            "ts": "1234.5678",
            "user": "U001",
            "text": "이건 수집 안 됨",
        }
        result = collector.collect(event)
        assert result is False

        messages = store.load_channel_buffer("C_OTHER")
        assert messages == []

    def test_collect_bot_message(self, collector, store):
        """봇 메시지도 수집 (관찰 대상)"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "UBOT",
            "text": "봇 메시지입니다",
            "bot_id": "B001",
        }
        collector.collect(event)

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["text"] == "봇 메시지입니다"

    def test_message_format(self, collector, store):
        """저장되는 메시지 포맷 검증"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "테스트 메시지",
            "thread_ts": "1234.0000",
        }
        collector.collect(event)

        messages = store.load_thread_buffer("C_OBSERVE", "1234.0000")
        msg = messages[0]
        assert "ts" in msg
        assert "user" in msg
        assert "text" in msg
        assert "thread_ts" in msg

    def test_disabled_collector(self, store):
        """target_channels가 비어있으면 수집하지 않음"""
        from seosoyoung.handlers.channel_collector import ChannelMessageCollector
        collector = ChannelMessageCollector(store=store, target_channels=[])

        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "수집 안 됨",
        }
        result = collector.collect(event)
        assert result is False

    def test_collect_multiple_messages(self, collector, store):
        """여러 메시지가 순서대로 누적됨"""
        for i in range(3):
            event = {
                "channel": "C_OBSERVE",
                "ts": f"1234.{i:04d}",
                "user": "U001",
                "text": f"메시지 {i}",
            }
            collector.collect(event)

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 3
        assert messages[0]["text"] == "메시지 0"
        assert messages[2]["text"] == "메시지 2"
