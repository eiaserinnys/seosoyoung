"""채널 메시지 수집기

관찰 대상 채널의 메시지를 ChannelStore 버퍼에 저장합니다.
"""

import logging

from seosoyoung.memory.channel_store import ChannelStore

logger = logging.getLogger(__name__)


class ChannelMessageCollector:
    """관찰 대상 채널의 메시지를 수집하여 버퍼에 저장"""

    # 수집 대상 subtype (내용이 있는 메시지)
    _COLLECTIBLE_SUBTYPES = {"bot_message", "message_changed", "me_message", "file_share"}
    # 명시적 스킵 subtype
    _SKIP_SUBTYPES = {
        "message_deleted", "channel_join", "channel_leave",
        "channel_topic", "channel_purpose", "channel_name",
        "channel_archive", "channel_unarchive",
        "group_join", "group_leave",
        "pinned_item", "unpinned_item",
    }

    def __init__(self, store: ChannelStore, target_channels: list[str]):
        self.store = store
        self.target_channels = set(target_channels)

    def collect(self, event: dict) -> bool:
        """이벤트에서 메시지를 추출하여 버퍼에 저장.

        Returns:
            True: 수집 성공, False: 대상이 아니거나 수집하지 않음
        """
        channel = event.get("channel", "")
        if not self.target_channels or channel not in self.target_channels:
            return False

        subtype = event.get("subtype")

        # 명시적 스킵 subtype
        if subtype in self._SKIP_SUBTYPES:
            return False

        # 알 수 없는 subtype도 스킵 (허용 목록 방식)
        if subtype and subtype not in self._COLLECTIBLE_SUBTYPES:
            return False

        # message_changed: 실제 내용은 event["message"] 안에 있음
        if subtype == "message_changed":
            source = event.get("message", {})
        else:
            source = event

        text = source.get("text", "")
        user = source.get("user", "")

        # text와 user 모두 비어있으면 수집하지 않음
        if not text and not user:
            return False

        ts = source.get("ts", "") or event.get("ts", "")
        bot_id = source.get("bot_id") or event.get("bot_id") or ""
        msg = {"ts": ts, "user": user, "text": text}
        if bot_id:
            msg["bot_id"] = bot_id

        thread_ts = source.get("thread_ts") or event.get("thread_ts")
        if thread_ts:
            msg["thread_ts"] = thread_ts
            self.store.append_thread_message(channel, thread_ts, msg)
        else:
            self.store.append_channel_message(channel, msg)

        return True

    def collect_reaction(self, event: dict, action: str) -> bool:
        """리액션 이벤트에서 reactions 필드를 갱신합니다.

        Args:
            event: reaction_added / reaction_removed 이벤트
            action: "added" | "removed"

        Returns:
            True: 갱신 성공, False: 대상이 아니거나 갱신하지 않음
        """
        item = event.get("item", {})
        if item.get("type") != "message":
            return False

        channel = item.get("channel", "")
        if not self.target_channels or channel not in self.target_channels:
            return False

        ts = item.get("ts", "")
        emoji = event.get("reaction", "")
        user = event.get("user", "")

        if not ts or not emoji:
            return False

        self.store.update_reactions(
            channel, ts=ts, emoji=emoji, user=user, action=action,
        )
        return True
