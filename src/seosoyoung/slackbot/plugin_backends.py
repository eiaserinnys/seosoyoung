"""Plugin SDK backend implementations.

This module provides the actual implementations of plugin_sdk APIs.
Called during startup to inject backends into plugin_sdk modules.

These backends wrap the existing seosoyoung infrastructure
(slack_client, claude executor, session manager, etc.)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from seosoyoung.plugin_sdk import slack, soulstream, mention
from seosoyoung.plugin_sdk.slack import (
    Message,
    ReactionResult,
    SendMessageResult,
    SlackBackend,
    UserInfo,
)
from seosoyoung.plugin_sdk.soulstream import (
    CompactResult,
    RunResult,
    RunStatus,
    SoulstreamBackend,
)

if TYPE_CHECKING:
    from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker
    from seosoyoung.slackbot.soulstream.session import SessionManager

logger = logging.getLogger(__name__)


# ============================================================================
# Slack Backend Implementation
# ============================================================================


class SlackBackendImpl(SlackBackend):
    """Slack backend implementation using slack_sdk client."""

    def __init__(self, client):
        """Initialize with Slack WebClient.

        Args:
            client: slack_sdk.WebClient instance
        """
        self._client = client

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Send a message to a channel."""
        try:
            result = self._client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                **kwargs,
            )
            return SendMessageResult(
                ok=True,
                ts=result.get("ts", ""),
                channel=result.get("channel", channel),
            )
        except Exception as e:
            logger.error(f"send_message failed: {e}")
            return SendMessageResult(ok=False, error=str(e))

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Update an existing message."""
        try:
            result = self._client.chat_update(
                channel=channel,
                ts=ts,
                text=text,
                **kwargs,
            )
            return SendMessageResult(
                ok=True,
                ts=result.get("ts", ts),
                channel=result.get("channel", channel),
            )
        except Exception as e:
            logger.error(f"update_message failed: {e}")
            return SendMessageResult(ok=False, error=str(e))

    async def add_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Add a reaction to a message."""
        try:
            self._client.reactions_add(
                channel=channel,
                timestamp=ts,
                name=emoji,
            )
            return ReactionResult(ok=True)
        except Exception as e:
            # Already reacted is not an error
            if "already_reacted" in str(e):
                return ReactionResult(ok=True)
            logger.error(f"add_reaction failed: {e}")
            return ReactionResult(ok=False, error=str(e))

    async def remove_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Remove a reaction from a message."""
        try:
            self._client.reactions_remove(
                channel=channel,
                timestamp=ts,
                name=emoji,
            )
            return ReactionResult(ok=True)
        except Exception as e:
            # Not reacted is not an error
            if "no_reaction" in str(e):
                return ReactionResult(ok=True)
            logger.error(f"remove_reaction failed: {e}")
            return ReactionResult(ok=False, error=str(e))

    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """Get information about a user."""
        try:
            result = self._client.users_info(user=user_id)
            user = result.get("user", {})
            profile = user.get("profile", {})
            return UserInfo(
                id=user.get("id", user_id),
                name=user.get("name", ""),
                real_name=profile.get("real_name", ""),
                display_name=profile.get("display_name", ""),
                is_bot=user.get("is_bot", False),
            )
        except Exception as e:
            logger.error(f"get_user_info failed: {e}")
            return None

    async def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get replies in a thread."""
        try:
            result = self._client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=limit,
            )
            messages = []
            for msg in result.get("messages", []):
                messages.append(
                    Message(
                        ts=msg.get("ts", ""),
                        text=msg.get("text", ""),
                        user=msg.get("user", ""),
                        thread_ts=msg.get("thread_ts"),
                        channel=channel,
                    )
                )
            return messages
        except Exception as e:
            logger.error(f"get_thread_replies failed: {e}")
            return []

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get recent messages in a channel."""
        try:
            result = self._client.conversations_history(
                channel=channel,
                limit=limit,
            )
            messages = []
            for msg in result.get("messages", []):
                messages.append(
                    Message(
                        ts=msg.get("ts", ""),
                        text=msg.get("text", ""),
                        user=msg.get("user", ""),
                        thread_ts=msg.get("thread_ts"),
                        channel=channel,
                    )
                )
            return messages
        except Exception as e:
            logger.error(f"get_channel_history failed: {e}")
            return []

    async def open_dm(self, user_id: str) -> str | None:
        """Open a DM channel with a user."""
        try:
            result = self._client.conversations_open(users=user_id)
            return result.get("channel", {}).get("id")
        except Exception as e:
            logger.error(f"open_dm failed: {e}")
            return None


# ============================================================================
# Soulstream Backend Implementation
# ============================================================================


class SoulstreamBackendImpl(SoulstreamBackend):
    """Soulstream backend implementation using ClaudeExecutor."""

    def __init__(
        self,
        executor,
        session_manager: "SessionManager",
        restart_manager,
        data_dir: Path,
        slack_client=None,
        update_message_fn=None,
    ):
        """Initialize with Claude executor and session manager.

        Args:
            executor: ClaudeExecutor.run bound method
            session_manager: SessionManager instance
            restart_manager: RestartManager instance
            data_dir: Data directory for plugin storage
            slack_client: Slack WebClient instance (for auto-constructing PresentationContext)
            update_message_fn: (client, channel, ts, text, *, blocks=None) -> None
                               전달하면 on_progress/on_compact가 None일 때 자동 생성됨
        """
        self._executor = executor
        self._session_manager = session_manager
        self._restart_manager = restart_manager
        self._data_dir = data_dir
        self._slack_client = slack_client
        self._update_message_fn = update_message_fn

    def _build_presentation(
        self,
        channel: str,
        thread_ts: str,
        msg_ts: str,
        session_id: str | None,
        role: str,
        *,
        dm_channel_id: str | None = None,
        dm_thread_ts: str | None = None,
    ):
        """presentation이 전달되지 않은 호출(워처 등)을 위해 PresentationContext를 자동 구성.

        slack_client가 없으면 RuntimeError를 발생시킵니다.
        """
        if self._slack_client is None:
            raise RuntimeError(
                "SoulstreamBackendImpl에 slack_client가 설정되지 않아 "
                "PresentationContext를 자동 구성할 수 없습니다. "
                "init_plugin_backends 호출 시 slack_client를 전달하세요."
            )

        from seosoyoung.slackbot.presentation.types import PresentationContext

        client = self._slack_client

        def say(*, text: str, thread_ts: str | None = None, **kw):
            client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                **kw,
            )

        return PresentationContext(
            channel=channel,
            thread_ts=thread_ts,
            msg_ts=msg_ts,
            say=say,
            client=client,
            effective_role=role,
            session_id=session_id,
            last_msg_ts=thread_ts,
            is_trello_mode=True,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
        )

    async def run(
        self,
        prompt: str,
        channel: str,
        thread_ts: str,
        role: str = "admin",
        session_id: str | None = None,
        on_progress=None,
        on_compact=None,
        **kwargs: Any,
    ) -> RunResult:
        """Execute Claude Code with the given prompt."""
        try:
            # Get or use provided session_id
            if session_id is None:
                session = self._session_manager.get(thread_ts)
                if session:
                    session_id = session.session_id

            # Resolve presentation context
            presentation = kwargs.get("presentation")
            if presentation is None:
                presentation = self._build_presentation(
                    channel=channel,
                    thread_ts=thread_ts,
                    msg_ts=kwargs.get("msg_ts", thread_ts),
                    session_id=session_id,
                    role=role,
                    dm_channel_id=kwargs.get("dm_channel_id"),
                    dm_thread_ts=kwargs.get("dm_thread_ts"),
                )

            # Auto-build progress callbacks when not provided
            if on_progress is None and self._update_message_fn is not None:
                from seosoyoung.slackbot.presentation.progress import build_progress_callbacks
                on_progress, on_compact = build_progress_callbacks(
                    presentation, self._update_message_fn,
                )

            # Run executor (this is synchronous internally)
            self._executor(
                prompt=prompt,
                thread_ts=thread_ts,
                msg_ts=kwargs.get("msg_ts", thread_ts),
                on_progress=on_progress,
                on_compact=on_compact,
                presentation=presentation,
                session_id=session_id,
                role=role,
            )

            # Get updated session_id
            session = self._session_manager.get(thread_ts)
            new_session_id = session.session_id if session else session_id

            return RunResult(
                ok=True,
                status=RunStatus.COMPLETED,
                session_id=new_session_id,
            )
        except Exception as e:
            logger.error(f"soulstream.run failed: {e}")
            return RunResult(
                ok=False,
                status=RunStatus.FAILED,
                error=str(e),
            )

    async def compact(self, session_id: str) -> CompactResult:
        """Compact a Claude Code session."""
        try:
            from seosoyoung.slackbot.soulstream import get_claude_runner

            runner = get_claude_runner()
            result = await runner.compact_session(session_id)

            if result.success:
                return CompactResult(
                    ok=True,
                    session_id=result.session_id,
                )
            else:
                return CompactResult(
                    ok=False,
                    error=result.error or "Compact failed",
                )
        except Exception as e:
            logger.error(f"soulstream.compact failed: {e}")
            return CompactResult(ok=False, error=str(e))

    def get_session_id(self, thread_ts: str) -> str | None:
        """Get the Claude Code session ID for a thread."""
        session = self._session_manager.get(thread_ts)
        return session.session_id if session else None

    def is_restart_pending(self) -> bool:
        """Check if a restart is pending."""
        return self._restart_manager.is_pending

    def get_data_dir(self) -> Path:
        """Get the data directory for plugin storage."""
        return self._data_dir


# ============================================================================
# Mention Tracking Backend Implementation
# ============================================================================


class MentionTrackingBackendImpl:
    """Mention tracking backend wrapping the existing MentionTracker."""

    def __init__(self, tracker: "MentionTracker"):
        self._tracker = tracker

    def mark(self, thread_ts: str) -> None:
        self._tracker.mark(thread_ts)

    def is_handled(self, thread_ts: str) -> bool:
        return self._tracker.is_handled(thread_ts)

    def unmark(self, thread_ts: str) -> None:
        self._tracker.unmark(thread_ts)


# ============================================================================
# Initialization
# ============================================================================


def init_plugin_backends(
    slack_client,
    executor,
    session_manager: "SessionManager",
    restart_manager,
    data_dir: Path,
    update_message_fn=None,
    mention_tracker: "MentionTracker | None" = None,
) -> None:
    """Initialize plugin SDK backends.

    Call this during startup after slack_client and executor are ready.

    Args:
        slack_client: Slack WebClient instance
        executor: ClaudeExecutor instance
        session_manager: SessionManager instance
        restart_manager: RestartManager instance
        data_dir: Data directory for plugin storage
        update_message_fn: (client, channel, ts, text, *, blocks=None) -> None
                           전달하면 워처 등에서 on_progress/on_compact가 자동 생성됨
        mention_tracker: MentionTracker instance for mention tracking backend
    """
    # Initialize Slack backend
    slack_backend = SlackBackendImpl(slack_client)
    slack.set_backend(slack_backend)
    logger.info("plugin_sdk.slack backend initialized")

    # Initialize Soulstream backend
    soulstream_backend = SoulstreamBackendImpl(
        executor, session_manager, restart_manager, data_dir,
        slack_client=slack_client,
        update_message_fn=update_message_fn,
    )
    soulstream.set_backend(soulstream_backend)
    logger.info("plugin_sdk.soulstream backend initialized")

    # Initialize Mention tracking backend
    if mention_tracker is not None:
        mention_backend = MentionTrackingBackendImpl(mention_tracker)
        mention.set_backend(mention_backend)
        logger.info("plugin_sdk.mention backend initialized")
