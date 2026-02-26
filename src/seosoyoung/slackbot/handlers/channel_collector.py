"""채널 메시지 수집기

관찰 대상 채널의 메시지를 ChannelStore 버퍼에 저장합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from seosoyoung.slackbot.memory.channel_store import ChannelStore

if TYPE_CHECKING:
    from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker

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

    def __init__(
        self,
        store: ChannelStore,
        target_channels: list[str],
        mention_tracker: MentionTracker | None = None,
        bot_user_id: str | None = None,
    ):
        self.store = store
        self.target_channels = set(target_channels)
        self.mention_tracker = mention_tracker
        self._bot_user_id = bot_user_id

    @property
    def bot_user_id(self) -> str | None:
        """봇 사용자 ID (런타임에 설정될 수 있으므로 프로퍼티로 제공)"""
        if self._bot_user_id:
            return self._bot_user_id
        # Config에서 런타임에 설정된 BOT_USER_ID를 참조
        try:
            from seosoyoung.slackbot.config import Config
            return Config.slack.bot_user_id
        except Exception:
            return None

    def _detect_and_mark_mention(self, text: str, ts: str, thread_ts: str | None) -> bool:
        """메시지 텍스트에 봇 멘션이 포함되어 있으면 mention_tracker에 마킹.

        Returns:
            True: 봇 멘션이 포함된 메시지 (멘션 스레드), False: 일반 메시지
        """
        if not self.mention_tracker:
            return False

        bot_id = self.bot_user_id
        if not bot_id:
            return False

        mention_tag = f"<@{bot_id}>"
        if mention_tag not in text:
            return False

        # 봇 멘션이 포함된 메시지: 해당 스레드를 마킹
        if thread_ts:
            self.mention_tracker.mark(thread_ts)
        else:
            # 채널 루트 메시지에서 멘션: ts 자체가 스레드 루트가 됨
            self.mention_tracker.mark(ts)

        return True

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
        files = source.get("files") or event.get("files")

        # text와 user 모두 비어있고 파일도 없으면 수집하지 않음
        if not text and not user and not files:
            return False

        ts = source.get("ts", "") or event.get("ts", "")
        thread_ts = source.get("thread_ts") or event.get("thread_ts")

        # 봇 멘션 자동 감지 및 마킹 (마킹만 수행, 수집은 계속 진행)
        # 멘션 스레드 메시지도 pending/thread_buffers에 정상 수집하여
        # 파이프라인에서 소화(consume)할 수 있도록 합니다.
        # 리액션/개입 필터링은 파이프라인(channel_pipeline.py)에서 처리합니다.
        self._detect_and_mark_mention(text, ts, thread_ts)

        bot_id = source.get("bot_id") or event.get("bot_id") or ""
        msg = {"ts": ts, "user": user, "text": text}
        if bot_id:
            msg["bot_id"] = bot_id
        if files:
            msg["files"] = [
                {"name": f.get("name", ""), "filetype": f.get("filetype", "")}
                for f in files
            ]

        # message_changed(unfurl 등)는 기존 메시지를 교체(upsert)하여 중복 방지
        is_update = subtype == "message_changed"
        if thread_ts:
            msg["thread_ts"] = thread_ts
            if is_update:
                self.store.upsert_thread_message(channel, thread_ts, msg)
            else:
                self.store.append_thread_message(channel, thread_ts, msg)
        else:
            if is_update:
                self.store.upsert_pending(channel, msg)
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
