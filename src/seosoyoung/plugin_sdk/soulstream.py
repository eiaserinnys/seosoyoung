"""Soulstream API for plugins.

Provides an interface for plugins to request Claude Code execution.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import soulstream

    # Request Claude Code execution
    result = await soulstream.run(
        prompt="Analyze this code...",
        channel="C12345",
        thread_ts="1234567890.123456",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol


# ============================================================================
# Type definitions
# ============================================================================


class RunStatus(Enum):
    """Status of a Soulstream run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunRequest:
    """Request to run Claude Code.

    This is what plugins return to request Claude Code execution.
    The host handles the actual execution.
    """

    prompt: str
    channel: str
    thread_ts: str
    role: str = "admin"
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Result of a Soulstream run."""

    ok: bool
    status: RunStatus = RunStatus.PENDING
    session_id: str | None = None
    error: str = ""
    output: str = ""


@dataclass
class CompactResult:
    """Result of a session compact operation."""

    ok: bool
    session_id: str | None = None
    error: str = ""


# ============================================================================
# Callback types
# ============================================================================

CompactCallback = Callable[[str], None]


# ============================================================================
# Backend Protocol (implemented by host)
# ============================================================================


class SoulstreamBackend(Protocol):
    """Protocol for Soulstream backend implementation.

    The host provides an implementation of this protocol.
    """

    async def run(
        self,
        prompt: str,
        channel: str,
        thread_ts: str,
        role: str = "admin",
        session_id: str | None = None,
        on_compact: CompactCallback | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Execute Claude Code with the given prompt.

        Args:
            prompt: The prompt to send to Claude Code
            channel: Slack channel ID for output
            thread_ts: Thread timestamp for output
            role: User role (affects permissions)
            session_id: Existing session ID to resume
            on_compact: Compact notification callback
            **kwargs: Additional arguments

        Returns:
            RunResult with status and output
        """
        ...

    async def compact(self, session_id: str) -> CompactResult:
        """Compact a Claude Code session to reduce context size.

        Args:
            session_id: Session ID to compact

        Returns:
            CompactResult with new session_id if changed
        """
        ...

    def get_session_id(self, thread_ts: str) -> str | None:
        """Get the Claude Code session ID for a thread.

        Args:
            thread_ts: Thread timestamp

        Returns:
            Session ID or None if no session exists
        """
        ...

    def is_restart_pending(self) -> bool:
        """Check if a restart is pending.

        Returns:
            True if restart is pending, False otherwise
        """
        ...

    def get_data_dir(self) -> Path:
        """Get the data directory for plugin storage.

        Returns:
            Path to data directory
        """
        ...


# ============================================================================
# Module-level backend registry
# ============================================================================

_backend: SoulstreamBackend | None = None


def set_backend(backend: SoulstreamBackend) -> None:
    """Set the Soulstream backend implementation.

    Called by the host during startup to provide the actual implementation.
    """
    global _backend
    _backend = backend


def get_backend() -> SoulstreamBackend | None:
    """Get the current Soulstream backend."""
    return _backend


def _require_backend() -> SoulstreamBackend:
    """Get backend or raise if not set."""
    if _backend is None:
        raise RuntimeError(
            "Soulstream backend not initialized. "
            "This should be set by the host during startup."
        )
    return _backend


# ============================================================================
# Public API functions
# ============================================================================


async def run(
    prompt: str,
    channel: str,
    thread_ts: str,
    role: str = "admin",
    session_id: str | None = None,
    on_compact: CompactCallback | None = None,
    **kwargs: Any,
) -> RunResult:
    """Execute Claude Code with the given prompt.

    This is the main entry point for plugins to run Claude Code.

    Args:
        prompt: The prompt to send to Claude Code
        channel: Slack channel ID for output
        thread_ts: Thread timestamp for output
        role: User role (affects permissions)
        session_id: Existing session ID to resume
        on_compact: Callback for compact notifications
        **kwargs: Additional arguments

    Returns:
        RunResult with status and output

    Example:
        result = await soulstream.run(
            prompt="What files are in this directory?",
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        if result.ok:
            print(f"Session: {result.session_id}")
    """
    backend = _require_backend()
    return await backend.run(
        prompt=prompt,
        channel=channel,
        thread_ts=thread_ts,
        role=role,
        session_id=session_id,
        on_compact=on_compact,
        **kwargs,
    )


async def compact(session_id: str) -> CompactResult:
    """Compact a Claude Code session to reduce context size.

    Compacting summarizes the conversation history to free up
    context window space for longer sessions.

    Args:
        session_id: Session ID to compact

    Returns:
        CompactResult with new session_id if changed

    Example:
        result = await soulstream.compact("session-abc123")
        if result.ok and result.session_id:
            print(f"New session: {result.session_id}")
    """
    backend = _require_backend()
    return await backend.compact(session_id)


def get_session_id(thread_ts: str) -> str | None:
    """Get the Claude Code session ID for a thread.

    Args:
        thread_ts: Thread timestamp

    Returns:
        Session ID or None if no session exists

    Example:
        session_id = soulstream.get_session_id("1234567890.123456")
        if session_id:
            await soulstream.compact(session_id)
    """
    backend = _require_backend()
    return backend.get_session_id(thread_ts)


def is_restart_pending() -> bool:
    """Check if a system restart is pending.

    When a restart is pending, plugins should avoid starting new tasks.

    Returns:
        True if restart is pending, False otherwise

    Example:
        if soulstream.is_restart_pending():
            await slack.send_message(
                channel=channel,
                text="재시작을 대기하는 중입니다."
            )
            return
    """
    backend = _require_backend()
    return backend.is_restart_pending()


def get_data_dir() -> Path:
    """Get the data directory for plugin storage.

    Returns:
        Path to data directory where plugins can store state files

    Example:
        data_dir = soulstream.get_data_dir()
        plugin_dir = data_dir / "my_plugin"
        plugin_dir.mkdir(exist_ok=True)
    """
    backend = _require_backend()
    return backend.get_data_dir()
