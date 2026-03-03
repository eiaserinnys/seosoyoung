# Seosoyoung Plugin SDK

Plugin SDK for seosoyoung slackbot - provides interface definitions and backend abstractions for plugin development.

## Overview

This SDK provides the core interfaces and abstractions needed to develop plugins for the seosoyoung slackbot:

- **Hook System**: `HookContext`, `HookResult`, plugin lifecycle hooks
- **Plugin Base**: `Plugin` base class and `PluginMeta` metadata
- **Backend Abstractions**:
  - `slack`: Async Slack API (send_message, add_reaction, remove_reaction, open_dm)
  - `soulstream`: Async Claude Code execution API (run, compact, get_session_id)

## Dependencies

This package has **zero external dependencies** - it only uses Python standard library.

## Usage

Plugins should depend on this SDK package and use the provided interfaces:

```python
from seosoyoung.plugin_sdk import Plugin, HookContext, HookResult
from seosoyoung.plugin_sdk import slack, soulstream

class MyPlugin(Plugin):
    async def on_message(self, ctx: HookContext):
        await slack.send_message(channel="C123", text="Hello!")
        return HookResult.SKIP, None
```

## Installation

For plugin development:

```bash
pip install git+https://github.com/eiaserinnys/seosoyoung.git#subdirectory=src/seosoyoung/plugin_sdk
```

Or in pyproject.toml:

```toml
dependencies = [
    "seosoyoung-plugin-sdk @ git+https://github.com/eiaserinnys/seosoyoung.git#subdirectory=src/seosoyoung/plugin_sdk"
]
```

## License

MIT
