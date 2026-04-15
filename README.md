# SeoSoyoung

A Slack bot that connects to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) via [Soulstream](https://github.com/eiaserinnys/soulstream), enabling AI-powered task execution directly from Slack conversations.

When you mention the bot in Slack, it delegates work to a Claude Code session and streams the results back to your thread in real time.

## How It Works

```
User: @seosoyoung "refactor the auth module"
  ↓
Slack Bot (Socket Mode)
  ↓
Soulstream (Claude Code host)
  ↓
Claude Code session executes the task
  ↓
Results streamed back to the Slack thread
```

1. A user mentions the bot in a Slack channel or thread.
2. The bot creates a Claude Code session through Soulstream (an HTTP/SSE service that hosts Claude Code).
3. As Claude Code works, progress updates are streamed to the Slack thread.
4. The final result is posted as a reply. Thread context is preserved for follow-up messages.

## Features

- **Claude Code Integration** — Delegates tasks to Claude Code sessions via Soulstream, with real-time SSE streaming of progress and results.
- **Thread-based Sessions** — Each Slack thread maps to a Claude Code session. Follow-up messages in the same thread continue the conversation.
- **Plugin System** — Extensible via plugins loaded from a YAML registry. Plugins can hook into the message lifecycle (pre-process, post-process, etc.). See [seosoyoung-plugins](https://github.com/eiaserinnys/seosoyoung-plugins) for available plugins.
- **MCP Server** — A built-in MCP (Model Context Protocol) server that provides tools for Slack messaging, file attachment, image generation, thread file downloads, and user profile lookups. Claude Code sessions use these tools to interact with Slack.
- **Role-based Access Control** — Configurable permission levels (operator, member, guest) to control who can invoke the bot.
- **Rescue Bot** — A lightweight fallback bot that runs independently. If the main bot goes down, the rescue bot can still handle basic requests using the Claude Code SDK directly.

## Architecture

The system runs as three independent processes, all managed by [Haniel](https://github.com/eiaserinnys/Haniel) (a service orchestrator):

| Process | Description | Port |
|---------|-------------|------|
| `bot` | Main Slack bot — handles events, manages sessions, runs plugins | 3106 |
| `mcp-seosoyoung` | MCP server — provides Slack tools to Claude Code sessions | 3104 |
| `rescue-bot` | Fallback bot — minimal Claude Code integration without plugins | 3107 |

```
[Haniel]                   ← Service orchestrator
  │
  ├── bot                  ← Slack Socket Mode bot
  │     ├── handlers/      ← Mention, message, command handlers
  │     ├── soulstream/    ← HTTP/SSE client to Soulstream
  │     ├── presentation/  ← Progress display in Slack
  │     └── plugins        ← Plugin manager + loaded plugins
  │
  ├── mcp-seosoyoung       ← MCP server (FastMCP)
  │     └── tools/         ← slack_post_message, attach_file, generate_image, ...
  │
  └── rescue-bot           ← Standalone fallback bot
```

### Soulstream Integration

The bot does **not** run Claude Code directly. Instead, it communicates with [Soulstream](https://github.com/eiaserinnys/soulstream), which manages Claude Code runner pools, session lifecycle, and credential profiles.

- **Request**: The bot sends an HTTP request to Soulstream with the user's prompt and session context.
- **Streaming**: Soulstream streams back events (tool calls, text output, errors) via SSE.
- **Presentation**: The bot's presentation module renders these events into Slack messages with live progress updates.

## Plugin System

Plugins extend the bot's behavior without modifying core code. They are loaded dynamically at startup from a YAML registry.

```yaml
# config/plugins.yaml
plugins:
  - name: memory
    module: seosoyoung_plugins.memory
    enabled: true
  - name: channel-observer
    module: seosoyoung_plugins.channel_observer
    enabled: true
  - name: trello
    module: seosoyoung_plugins.trello
    enabled: true
  - name: translate
    module: seosoyoung_plugins.translate
    enabled: false
```

Plugin implementations live in a separate package: [seosoyoung-plugins](https://github.com/eiaserinnys/seosoyoung-plugins).

### Plugin SDK

The bot provides a Plugin SDK (`seosoyoung.plugin_sdk`) that plugins import to interact with the system:

```python
from seosoyoung.plugin_sdk import Plugin, PluginMeta, HookContext, HookResult
from seosoyoung.plugin_sdk import slack, soulstream, mention

class MyPlugin(Plugin):
    meta = PluginMeta(name="my-plugin", version="1.0.0", description="Example")

    async def on_load(self, config: dict) -> None:
        pass  # Initialize resources

    async def on_unload(self) -> None:
        pass  # Cleanup

    def register_hooks(self) -> dict:
        return {"message_received": self.on_message}

    async def on_message(self, ctx: HookContext) -> tuple[HookResult, any]:
        await slack.send_message(ctx.channel, "Got it!")
        return HookResult.CONTINUE, None
```

The SDK provides three backend interfaces:
- `slack` — Send messages, add reactions, look up users
- `soulstream` — Run Claude Code sessions, compact context
- `mention` — Track which threads have been handled

## Project Structure

```
src/seosoyoung/
├── slackbot/              # Main bot application
│   ├── main.py            # Entry point, app initialization
│   ├── config.py          # Environment-based configuration
│   ├── handlers/          # Slack event handlers (mention, message, commands)
│   ├── soulstream/        # Soulstream HTTP/SSE client, session management
│   ├── presentation/      # Live progress rendering in Slack
│   ├── slack/             # Slack API helpers (formatting, message utils)
│   └── auth.py            # Role-based access control
├── core/                  # Plugin infrastructure
│   ├── plugin_manager.py  # Dynamic plugin loading and lifecycle
│   ├── plugin.py          # Base plugin class (internal)
│   ├── hooks.py           # Hook chain execution engine
│   ├── context.py         # Shared context object
│   └── plugin_config.py   # YAML registry and config loading
├── plugin_sdk/            # Public SDK for plugin development
│   ├── plugin.py          # Plugin base class and metadata
│   ├── hooks.py           # HookContext, HookResult, HookPriority
│   ├── slack.py           # Slack backend protocol
│   ├── soulstream.py      # Soulstream backend protocol
│   └── mention.py         # Mention tracking backend protocol
├── mcp/                   # MCP server (mcp-seosoyoung)
│   ├── server.py          # FastMCP server setup
│   └── tools/             # Tool implementations
│       ├── slack_messaging.py   # Post messages to Slack
│       ├── attach.py            # Attach files to threads
│       ├── image_gen.py         # Generate images (Gemini)
│       ├── thread_files.py      # Download thread attachments
│       └── user_profile.py      # Look up Slack user profiles
├── rescue/                # Rescue bot (fallback)
└── utils/                 # Shared utilities
```

## Prerequisites

- **Python 3.11+**
- **Slack App** — Create one at [api.slack.com/apps](https://api.slack.com/apps) with:
  - Socket Mode enabled
  - Bot Token Scopes: `app_mentions:read`, `chat:write`, `files:write`, `channels:history`, `groups:history`
  - Event Subscriptions: `app_mention`, `message.channels`
- **Soulstream** — A running [Soulstream](https://github.com/eiaserinnys/soulstream) instance for Claude Code execution
- **Haniel** (optional) — [Haniel](https://github.com/eiaserinnys/Haniel) for automated deployment and service management

## Installation

### With Haniel (recommended)

[Haniel](https://github.com/eiaserinnys/Haniel) automates the entire setup: repository cloning, virtual environments, dependency installation, `.env` configuration, and service registration. Refer to the Haniel documentation for initial installation and configuration.

### Manual Setup

```bash
# Clone the repository
git clone https://github.com/eiaserinnys/seosoyoung.git
cd seosoyoung

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies and the package
# (requirements.txt lists all runtime dependencies;
#  pip install -e . registers the package for imports)
pip install -r requirements.txt
pip install -e .

# Configure environment variables
cp .env.example .env
# Edit .env with your Slack tokens, Soulstream URL, etc.

# Set up plugin configuration
# Create config/plugins.yaml using the format shown in the Plugin System section above
# Each plugin may also need its own config file in config/ (e.g., trello.yaml, memory.yaml)

# Run the bot
python -m seosoyoung.slackbot.main

# Run the MCP server (separate process)
python -m seosoyoung.mcp
```

## Configuration

The bot is configured through environment variables (typically in a `.env` file):

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack app-level token for Socket Mode (`xapp-...`) |
| `SOULSTREAM_URL` | Soulstream server URL (e.g., `http://localhost:4105`) |
| `OPERATOR_USER_ID` | Slack user ID for the bot operator |
| `BOT_USER_ID` | The bot's own Slack user ID |

See `.env.example` (if available) or the Haniel configuration for the full list. Plugin-specific settings live in `config/*.yaml` files (gitignored). See each plugin's documentation for required settings.

## Testing

```bash
pytest
```

## License

[MIT](LICENSE)
