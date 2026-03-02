"""Plugin SDK - interfaces for plugin development.

This module exposes the public API that plugins should import.
Plugins depend ONLY on plugin_sdk, not on core.
"""

from seosoyoung.plugin_sdk.hooks import (
    HookContext,
    HookPriority,
    HookResult,
)
from seosoyoung.plugin_sdk.plugin import (
    HookHandler,
    Plugin,
    PluginMeta,
)

__all__ = [
    "HookContext",
    "HookPriority",
    "HookResult",
    "HookHandler",
    "Plugin",
    "PluginMeta",
]
