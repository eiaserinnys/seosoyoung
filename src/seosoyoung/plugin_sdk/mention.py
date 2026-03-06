"""Mention tracking API for plugins.

Provides an interface for plugins to check whether a thread is being
handled by the mention handler, preventing duplicate interventions.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import mention

    # Check if a thread is already handled
    if mention.is_handled(thread_ts):
        return  # skip intervention

    # Mark a thread as being handled
    mention.mark(thread_ts)
"""

from __future__ import annotations

from typing import Protocol


# ============================================================================
# Backend Protocol (implemented by host)
# ============================================================================


class MentionTrackingBackend(Protocol):
    """Protocol for mention tracking backend implementation.

    The host provides an implementation of this protocol.
    """

    def mark(self, thread_ts: str) -> None:
        """Register a thread as being handled by mention handler."""
        ...

    def is_handled(self, thread_ts: str) -> bool:
        """Check whether a thread is currently handled by mention handler."""
        ...

    def unmark(self, thread_ts: str) -> None:
        """Remove a thread from tracking."""
        ...


# ============================================================================
# Module-level backend registry
# ============================================================================

_backend: MentionTrackingBackend | None = None


def set_backend(backend: MentionTrackingBackend) -> None:
    """Set the mention tracking backend implementation.

    Called by the host during startup to provide the actual implementation.
    """
    global _backend
    _backend = backend


def get_backend() -> MentionTrackingBackend | None:
    """Get the current mention tracking backend."""
    return _backend


def _require_backend() -> MentionTrackingBackend:
    """Get backend or raise if not set."""
    if _backend is None:
        raise RuntimeError(
            "Mention tracking backend not initialized. "
            "This should be set by the host during startup."
        )
    return _backend


# ============================================================================
# Public API functions
# ============================================================================


def mark(thread_ts: str) -> None:
    """Mark a thread as being handled by the mention handler.

    Args:
        thread_ts: Thread timestamp to mark
    """
    _require_backend().mark(thread_ts)


def is_handled(thread_ts: str) -> bool:
    """Check if a thread is currently being handled by mention handler.

    Args:
        thread_ts: Thread timestamp to check

    Returns:
        True if the thread is being handled, False otherwise
    """
    return _require_backend().is_handled(thread_ts)


def unmark(thread_ts: str) -> None:
    """Remove a thread from mention tracking.

    Args:
        thread_ts: Thread timestamp to unmark
    """
    _require_backend().unmark(thread_ts)
