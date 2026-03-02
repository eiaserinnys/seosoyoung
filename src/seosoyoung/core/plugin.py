"""Plugin base class and metadata.

DEPRECATED: Import from seosoyoung.plugin_sdk instead.
This module re-exports from plugin_sdk for backward compatibility.
"""

from seosoyoung.plugin_sdk.plugin import (
    HookHandler,
    Plugin,
    PluginMeta,
)

__all__ = [
    "HookHandler",
    "Plugin",
    "PluginMeta",
]
