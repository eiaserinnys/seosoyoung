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
        context: list[dict] | None = None,
        folder_id: str | None = None,
        system_prompt: str | None = None,
        agent_id: str | None = None,
        caller_info: dict | None = None,
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
            context: Structured context items for soulstream assembly
            folder_id: Soulstream folder ID to place the session in
            system_prompt: Claude API system 파라미터로 전달할 시스템 프롬프트
            agent_id: soul-server 에이전트 프로필 ID
            caller_info: 호출 출처를 식별하는 v1 caller_info dict (atom 스키마 ed3a216d).
                plugin_sdk helper로 조립 권장 (R-4 G-12 + R-5 G-15 §9 대칭):

                    from seosoyoung.plugin_sdk.caller_info import (
                        build_bot_caller_info,
                        build_slack_caller_info,
                        get_host_preferred_node,
                    )

                    # 자동 봇 (channel_observer / trello_watcher 등)
                    info = build_bot_caller_info(
                        source="channel_observer",
                        display_name="채널 관찰자",
                        agent_node=get_host_preferred_node(),
                    )

                    # 사용자 슬랙 진입 (reaction trigger 등) — R-5 G-15
                    user = await slack.get_user_info(user_id)
                    info = build_slack_caller_info(
                        channel_id=channel, user_id=user_id, thread_ts=thread_ts,
                        display_name=(user.display_name or user.real_name) if user else None,
                        avatar_url=user.avatar_url if user else None,
                        email=user.email if user else None,
                    )

                orch-server 푸시 알림 필터링과 세션 관찰성에 사용된다.
                단일 키 dict (source만 박는 패턴)는 deprecated (R-4 G-12) — display_name/
                avatar_url 부재 시 unified-dashboard owner fallback 발동
                (R-2 G-9 회귀 부류).
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
    context: list[dict] | None = None,
    folder_id: str | None = None,
    system_prompt: str | None = None,
    agent_id: str | None = None,
    caller_info: dict | None = None,
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
        context: Structured context items for soulstream assembly
        folder_id: Soulstream folder ID to place the session in
        system_prompt: Claude API system 파라미터로 전달할 시스템 프롬프트
        agent_id: soul-server 에이전트 프로필 ID
        caller_info: 호출 출처를 식별하는 v1 caller_info dict (atom 스키마 ed3a216d).
            plugin_sdk helper로 조립 권장 (R-4 G-12 + R-5 G-15 §9 대칭):

                from seosoyoung.plugin_sdk.caller_info import (
                    build_bot_caller_info,
                    build_slack_caller_info,
                    get_host_preferred_node,
                )

                # 자동 봇 (channel_observer / trello_watcher 등)
                info = build_bot_caller_info(
                    source="channel_observer",
                    display_name="채널 관찰자",
                    agent_node=get_host_preferred_node(),
                )

                # 사용자 슬랙 진입 (reaction trigger 등) — R-5 G-15
                user = await slack.get_user_info(user_id)
                info = build_slack_caller_info(
                    channel_id=channel, user_id=user_id, thread_ts=thread_ts,
                    display_name=(user.display_name or user.real_name) if user else None,
                    avatar_url=user.avatar_url if user else None,
                    email=user.email if user else None,
                )

            orch-server 푸시 알림 필터링과 세션 관찰성에 사용된다.
            단일 키 dict (source만 박는 패턴)는 deprecated (R-4 G-12) — display_name/
            avatar_url 부재 시 unified-dashboard owner fallback 발동
            (R-2 G-9 회귀 부류).
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
        context=context,
        folder_id=folder_id,
        system_prompt=system_prompt,
        agent_id=agent_id,
        caller_info=caller_info,
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
