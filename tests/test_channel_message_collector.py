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


class TestReactionCollection:
    """리액션 이벤트 수집 테스트"""

    def test_collect_reaction_added(self, collector, store):
        """reaction_added 이벤트 수집"""
        # 먼저 메시지를 pending에 넣어놓음
        store.append_pending("C_OBSERVE", {"ts": "1234.5678", "user": "U001", "text": "hello"})

        event = {
            "type": "reaction_added",
            "reaction": "thumbsup",
            "user": "U002",
            "item": {
                "type": "message",
                "channel": "C_OBSERVE",
                "ts": "1234.5678",
            },
        }
        result = collector.collect_reaction(event, action="added")
        assert result is True

        msgs = store.load_pending("C_OBSERVE")
        reactions = msgs[0].get("reactions", [])
        assert len(reactions) == 1
        assert reactions[0]["name"] == "thumbsup"

    def test_collect_reaction_removed(self, collector, store):
        """reaction_removed 이벤트 수집"""
        store.append_pending("C_OBSERVE", {
            "ts": "1234.5678", "user": "U001", "text": "hello",
            "reactions": [{"name": "thumbsup", "users": ["U002"], "count": 1}],
        })

        event = {
            "type": "reaction_removed",
            "reaction": "thumbsup",
            "user": "U002",
            "item": {
                "type": "message",
                "channel": "C_OBSERVE",
                "ts": "1234.5678",
            },
        }
        result = collector.collect_reaction(event, action="removed")
        assert result is True

        msgs = store.load_pending("C_OBSERVE")
        reactions = msgs[0].get("reactions", [])
        assert len(reactions) == 0

    def test_collect_reaction_ignores_non_target_channel(self, collector, store):
        """대상 외 채널의 리액션은 무시"""
        event = {
            "type": "reaction_added",
            "reaction": "thumbsup",
            "user": "U002",
            "item": {
                "type": "message",
                "channel": "C_OTHER",
                "ts": "1234.5678",
            },
        }
        result = collector.collect_reaction(event, action="added")
        assert result is False

    def test_collect_reaction_ignores_non_message_item(self, collector, store):
        """메시지가 아닌 아이템(파일 등)에 대한 리액션은 무시"""
        event = {
            "type": "reaction_added",
            "reaction": "thumbsup",
            "user": "U002",
            "item": {
                "type": "file",
                "channel": "C_OBSERVE",
                "file": "F001",
            },
        }
        result = collector.collect_reaction(event, action="added")
        assert result is False


class TestSubtypeHandling:
    """subtype 이벤트 처리 테스트"""

    def test_message_changed_extracts_from_inner_message(self, collector, store):
        """message_changed subtype은 event['message']에서 text/user 추출"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "message_changed",
            "message": {
                "text": "URL이 포함된 메시지 https://example.com",
                "user": "U001",
                "ts": "1234.5678",
            },
            "text": "",
            "user": "",
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["text"] == "URL이 포함된 메시지 https://example.com"
        assert messages[0]["user"] == "U001"

    def test_message_deleted_is_skipped(self, collector, store):
        """message_deleted subtype은 수집하지 않음"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "message_deleted",
            "deleted_ts": "1234.0000",
        }
        result = collector.collect(event)
        assert result is False

        messages = store.load_channel_buffer("C_OBSERVE")
        assert messages == []

    def test_channel_join_is_skipped(self, collector, store):
        """channel_join subtype은 수집하지 않음"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "channel_join",
            "user": "U001",
            "text": "<@U001> has joined the channel",
        }
        result = collector.collect(event)
        assert result is False

    def test_empty_text_and_user_is_skipped(self, collector, store):
        """text와 user 모두 비어있으면 수집하지 않음"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "text": "",
            "user": "",
        }
        result = collector.collect(event)
        assert result is False

        messages = store.load_channel_buffer("C_OBSERVE")
        assert messages == []

    def test_bot_message_subtype_collected(self, collector, store):
        """bot_message subtype은 수집 (봇이 blocks/text로 보낸 메시지)"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "bot_message",
            "text": "봇이 보낸 알림",
            "bot_id": "B001",
            "username": "알림봇",
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["text"] == "봇이 보낸 알림"

    def test_message_changed_with_empty_inner_message_skipped(self, collector, store):
        """message_changed인데 inner message도 비어있으면 스킵"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "message_changed",
            "message": {
                "text": "",
                "user": "",
                "ts": "1234.5678",
            },
        }
        result = collector.collect(event)
        assert result is False

    def test_message_changed_thread_message(self, collector, store):
        """message_changed subtype의 스레드 메시지도 올바르게 수집"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.9999",
            "subtype": "message_changed",
            "message": {
                "text": "스레드에서 unfurl된 메시지",
                "user": "U002",
                "ts": "1234.9999",
                "thread_ts": "1234.0000",
            },
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_thread_buffer("C_OBSERVE", "1234.0000")
        assert len(messages) == 1
        assert messages[0]["text"] == "스레드에서 unfurl된 메시지"


class TestFileCollection:
    """파일(이미지 등) 첨부 메시지 수집 테스트"""

    def test_collect_image_only_message(self, collector, store):
        """text 없이 이미지만 있는 메시지도 수집"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "",
            "files": [
                {
                    "id": "F001",
                    "name": "screenshot.png",
                    "mimetype": "image/png",
                    "filetype": "png",
                }
            ],
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["files"] == [{"name": "screenshot.png", "filetype": "png"}]

    def test_collect_text_with_files(self, collector, store):
        """text와 파일이 모두 있는 메시지"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "이것 좀 봐주세요",
            "files": [
                {
                    "id": "F002",
                    "name": "design.pdf",
                    "mimetype": "application/pdf",
                    "filetype": "pdf",
                }
            ],
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["text"] == "이것 좀 봐주세요"
        assert messages[0]["files"] == [{"name": "design.pdf", "filetype": "pdf"}]

    def test_collect_multiple_files(self, collector, store):
        """여러 파일이 첨부된 메시지"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "",
            "files": [
                {"id": "F001", "name": "img1.png", "mimetype": "image/png", "filetype": "png"},
                {"id": "F002", "name": "img2.jpg", "mimetype": "image/jpeg", "filetype": "jpg"},
            ],
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert len(messages[0]["files"]) == 2

    def test_file_share_subtype_collected(self, collector, store):
        """file_share subtype도 수집"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "subtype": "file_share",
            "user": "U001",
            "text": "",
            "files": [
                {"id": "F001", "name": "doc.xlsx", "mimetype": "application/vnd.ms-excel", "filetype": "xlsx"},
            ],
        }
        result = collector.collect(event)
        assert result is True

        messages = store.load_channel_buffer("C_OBSERVE")
        assert len(messages) == 1
        assert messages[0]["files"] == [{"name": "doc.xlsx", "filetype": "xlsx"}]

    def test_no_files_key_means_no_files_field(self, collector, store):
        """files 키가 없는 일반 메시지에는 files 필드 없음"""
        event = {
            "channel": "C_OBSERVE",
            "ts": "1234.5678",
            "user": "U001",
            "text": "일반 텍스트 메시지",
        }
        collector.collect(event)

        messages = store.load_channel_buffer("C_OBSERVE")
        assert "files" not in messages[0]
