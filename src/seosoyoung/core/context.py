"""Hook context factory.

Provides a convenience function for creating HookContext instances.
"""

from __future__ import annotations

from typing import Any

from seosoyoung.core.hooks import HookContext


def create_hook_context(hook_name: str, **kwargs: Any) -> HookContext:
    """Create a HookContext with the given hook name and keyword arguments.

    Example::

        ctx = create_hook_context("on_message", text="hello", user="U123")
        # ctx.hook_name == "on_message"
        # ctx.args == {"text": "hello", "user": "U123"}
    """
    return HookContext(hook_name=hook_name, args=kwargs)
