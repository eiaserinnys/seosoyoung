"""Slack API for plugins.

Provides a clean interface for plugins to interact with Slack.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import slack

    # After host initialization
    await slack.send_message("C12345", "Hello!")
    await slack.add_reaction("C12345", "1234567890.123456", "thumbsup")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, TypeVar

T = TypeVar("T")


# ============================================================================
# Type definitions
# ============================================================================


@dataclass
class UserInfo:
    """Slack user information."""

    id: str
    name: str
    real_name: str = ""
    display_name: str = ""
    is_bot: bool = False


@dataclass
class Reaction:
    """Slack message reaction."""

    name: str        # 이모지 이름 (예: 'thumbsup')
    count: int       # 총 리액션 수
    users: list[str] = field(default_factory=list)  # 누른 user ID 목록


@dataclass
class FileInfo:
    """Slack file attachment info."""

    name: str
    title: str
    mimetype: str
    permalink: str   # 슬랙 내 링크


@dataclass
class Message:
    """Slack message information."""

    ts: str
    text: str
    user: str = ""
    thread_ts: str | None = None
    channel: str = ""
    # Rich data (Optional, 하위 호환)
    reactions: list[Reaction] = field(default_factory=list)
    files: list[FileInfo] = field(default_factory=list)
    blocks: list[dict] = field(default_factory=list)


@dataclass
class SendMessageResult:
    """Result of sending a message."""

    ok: bool
    ts: str = ""
    channel: str = ""
    error: str = ""


@dataclass
class ReactionResult:
    """Result of a reaction operation."""

    ok: bool
    error: str = ""


# ============================================================================
# Backend Protocol (implemented by host)
# ============================================================================


class SlackBackend(Protocol):
    """Protocol for Slack backend implementation.

    The host provides an implementation of this protocol.
    """

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Send a message to a channel."""
        ...

    async def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        **kwargs: Any,
    ) -> SendMessageResult:
        """Update an existing message."""
        ...

    async def add_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Add a reaction to a message."""
        ...

    async def remove_reaction(
        self,
        channel: str,
        ts: str,
        emoji: str,
    ) -> ReactionResult:
        """Remove a reaction from a message."""
        ...

    async def get_user_info(self, user_id: str) -> UserInfo | None:
        """Get information about a user."""
        ...

    async def get_thread_replies(
        self,
        channel: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get replies in a thread."""
        ...

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
    ) -> list[Message]:
        """Get recent messages in a channel."""
        ...

    async def open_dm(self, user_id: str) -> str | None:
        """Open a DM channel with a user. Returns channel ID."""
        ...


# ============================================================================
# Module-level backend registry
# ============================================================================

_backend: SlackBackend | None = None


def set_backend(backend: SlackBackend) -> None:
    """Set the Slack backend implementation.

    Called by the host during startup to provide the actual implementation.
    """
    global _backend
    _backend = backend


def get_backend() -> SlackBackend | None:
    """Get the current Slack backend."""
    return _backend


def _require_backend() -> SlackBackend:
    """Get backend or raise if not set."""
    if _backend is None:
        raise RuntimeError(
            "Slack backend not initialized. "
            "This should be set by the host during startup."
        )
    return _backend


# ============================================================================
# Public API functions
# ============================================================================


async def send_message(
    channel: str,
    text: str,
    thread_ts: str | None = None,
    **kwargs: Any,
) -> SendMessageResult:
    """Send a message to a Slack channel.

    Args:
        channel: Channel ID (e.g., "C12345678")
        text: Message text
        thread_ts: Thread timestamp to reply in a thread
        **kwargs: Additional arguments passed to Slack API

    Returns:
        SendMessageResult with ok, ts, channel, error fields
    """
    backend = _require_backend()
    return await backend.send_message(channel, text, thread_ts, **kwargs)


async def update_message(
    channel: str,
    ts: str,
    text: str,
    **kwargs: Any,
) -> SendMessageResult:
    """Update an existing message.

    Args:
        channel: Channel ID
        ts: Message timestamp
        text: New message text
        **kwargs: Additional arguments

    Returns:
        SendMessageResult with ok, ts, channel, error fields
    """
    backend = _require_backend()
    return await backend.update_message(channel, ts, text, **kwargs)


async def add_reaction(
    channel: str,
    ts: str,
    emoji: str,
) -> ReactionResult:
    """Add a reaction emoji to a message.

    Args:
        channel: Channel ID
        ts: Message timestamp
        emoji: Emoji name without colons (e.g., "thumbsup")

    Returns:
        ReactionResult with ok, error fields
    """
    backend = _require_backend()
    return await backend.add_reaction(channel, ts, emoji)


async def remove_reaction(
    channel: str,
    ts: str,
    emoji: str,
) -> ReactionResult:
    """Remove a reaction emoji from a message.

    Args:
        channel: Channel ID
        ts: Message timestamp
        emoji: Emoji name without colons

    Returns:
        ReactionResult with ok, error fields
    """
    backend = _require_backend()
    return await backend.remove_reaction(channel, ts, emoji)


async def get_user_info(user_id: str) -> UserInfo | None:
    """Get information about a Slack user.

    Args:
        user_id: User ID (e.g., "U12345678")

    Returns:
        UserInfo or None if not found
    """
    backend = _require_backend()
    return await backend.get_user_info(user_id)


async def get_thread_replies(
    channel: str,
    thread_ts: str,
    limit: int = 100,
) -> list[Message]:
    """Get replies in a thread.

    Args:
        channel: Channel ID
        thread_ts: Thread parent timestamp
        limit: Maximum number of messages to return

    Returns:
        List of Message objects
    """
    backend = _require_backend()
    return await backend.get_thread_replies(channel, thread_ts, limit)


async def get_channel_history(
    channel: str,
    limit: int = 100,
) -> list[Message]:
    """Get recent messages in a channel.

    Args:
        channel: Channel ID
        limit: Maximum number of messages to return

    Returns:
        List of Message objects
    """
    backend = _require_backend()
    return await backend.get_channel_history(channel, limit)


async def open_dm(user_id: str) -> str | None:
    """Open a DM channel with a user.

    Args:
        user_id: User ID

    Returns:
        DM channel ID or None if failed
    """
    backend = _require_backend()
    return await backend.open_dm(user_id)
