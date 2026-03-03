"""Plugin SDK - interfaces for plugin development.

This module exposes the public API that plugins should import.
Plugins depend ONLY on plugin_sdk, not on core.

Submodules:
    - slack: Slack API functions (send_message, add_reaction, etc.)
    - soulstream: Claude Code execution API (run, compact, etc.)

Usage:
    from seosoyoung.plugin_sdk import HookContext, HookResult, Plugin, PluginMeta
    from seosoyoung.plugin_sdk import slack, soulstream

    # Use Slack API
    await slack.send_message(channel, "Hello!")

    # Use Soulstream API
    await soulstream.run(prompt, channel, thread_ts)
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

# Import submodules for namespace access (e.g., sdk.slack.send_message)
from seosoyoung.plugin_sdk import slack
from seosoyoung.plugin_sdk import soulstream

# Also export commonly used types from submodules
from seosoyoung.plugin_sdk.slack import (
    Message,
    ReactionResult,
    SendMessageResult,
    SlackBackend,
    UserInfo,
)
from seosoyoung.plugin_sdk.soulstream import (
    CompactResult,
    RunRequest,
    RunResult,
    RunStatus,
    SoulstreamBackend,
)

__all__ = [
    # Core plugin types
    "HookContext",
    "HookPriority",
    "HookResult",
    "HookHandler",
    "Plugin",
    "PluginMeta",
    # Submodules
    "slack",
    "soulstream",
    # Slack types
    "Message",
    "ReactionResult",
    "SendMessageResult",
    "SlackBackend",
    "UserInfo",
    # Soulstream types
    "CompactResult",
    "RunRequest",
    "RunResult",
    "RunStatus",
    "SoulstreamBackend",
]
