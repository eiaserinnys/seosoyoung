"""Hook system primitives for the plugin architecture.

DEPRECATED: Import from seosoyoung.plugin_sdk instead.
This module re-exports from plugin_sdk for backward compatibility.
"""

from seosoyoung.plugin_sdk.hooks import (
    HookContext,
    HookPriority,
    HookResult,
)

__all__ = [
    "HookContext",
    "HookPriority",
    "HookResult",
]
