"""채널 메시지 수집기

관찰 대상 채널의 메시지를 ChannelStore 버퍼에 저장합니다.
"""

import logging

from seosoyoung.memory.channel_store import ChannelStore

logger = logging.getLogger(__name__)


class ChannelMessageCollector:
    """관찰 대상 채널의 메시지를 수집하여 버퍼에 저장"""

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

        msg = {
            "ts": event.get("ts", ""),
            "user": event.get("user", ""),
            "text": event.get("text", ""),
        }

        thread_ts = event.get("thread_ts")
        if thread_ts:
            msg["thread_ts"] = thread_ts
            self.store.append_thread_message(channel, thread_ts, msg)
        else:
            self.store.append_channel_message(channel, msg)

        return True
