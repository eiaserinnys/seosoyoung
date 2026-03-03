# plugin_sdk/slack.py

> 경로: `seosoyoung/plugin_sdk/slack.py`

## 개요

Slack API for plugins.

Provides a clean interface for plugins to interact with Slack.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import slack

    # After host initialization
    await slack.send_message("C12345", "Hello!")
    await slack.add_reaction("C12345", "1234567890.123456", "thumbsup")

## 클래스

### `UserInfo`
- 위치: 줄 28
- 설명: Slack user information.

### `Message`
- 위치: 줄 39
- 설명: Slack message information.

### `SendMessageResult`
- 위치: 줄 50
- 설명: Result of sending a message.

### `ReactionResult`
- 위치: 줄 60
- 설명: Result of a reaction operation.

### `SlackBackend` (Protocol)
- 위치: 줄 72
- 설명: Protocol for Slack backend implementation.

The host provides an implementation of this protocol.

#### 메서드

- `async send_message(self, channel, text, thread_ts)` (줄 78): Send a message to a channel.
- `async update_message(self, channel, ts, text)` (줄 88): Update an existing message.
- `async add_reaction(self, channel, ts, emoji)` (줄 98): Add a reaction to a message.
- `async remove_reaction(self, channel, ts, emoji)` (줄 107): Remove a reaction from a message.
- `async get_user_info(self, user_id)` (줄 116): Get information about a user.
- `async get_thread_replies(self, channel, thread_ts, limit)` (줄 120): Get replies in a thread.
- `async get_channel_history(self, channel, limit)` (줄 129): Get recent messages in a channel.
- `async open_dm(self, user_id)` (줄 137): Open a DM channel with a user. Returns channel ID.

## 함수

### `set_backend(backend)`
- 위치: 줄 149
- 설명: Set the Slack backend implementation.

Called by the host during startup to provide the actual implementation.

### `get_backend()`
- 위치: 줄 158
- 설명: Get the current Slack backend.

### `_require_backend()`
- 위치: 줄 163
- 설명: Get backend or raise if not set.

### `async send_message(channel, text, thread_ts)`
- 위치: 줄 178
- 설명: Send a message to a Slack channel.

Args:
    channel: Channel ID (e.g., "C12345678")
    text: Message text
    thread_ts: Thread timestamp to reply in a thread
    **kwargs: Additional arguments passed to Slack API

Returns:
    SendMessageResult with ok, ts, channel, error fields

### `async update_message(channel, ts, text)`
- 위치: 줄 199
- 설명: Update an existing message.

Args:
    channel: Channel ID
    ts: Message timestamp
    text: New message text
    **kwargs: Additional arguments

Returns:
    SendMessageResult with ok, ts, channel, error fields

### `async add_reaction(channel, ts, emoji)`
- 위치: 줄 220
- 설명: Add a reaction emoji to a message.

Args:
    channel: Channel ID
    ts: Message timestamp
    emoji: Emoji name without colons (e.g., "thumbsup")

Returns:
    ReactionResult with ok, error fields

### `async remove_reaction(channel, ts, emoji)`
- 위치: 줄 239
- 설명: Remove a reaction emoji from a message.

Args:
    channel: Channel ID
    ts: Message timestamp
    emoji: Emoji name without colons

Returns:
    ReactionResult with ok, error fields

### `async get_user_info(user_id)`
- 위치: 줄 258
- 설명: Get information about a Slack user.

Args:
    user_id: User ID (e.g., "U12345678")

Returns:
    UserInfo or None if not found

### `async get_thread_replies(channel, thread_ts, limit)`
- 위치: 줄 271
- 설명: Get replies in a thread.

Args:
    channel: Channel ID
    thread_ts: Thread parent timestamp
    limit: Maximum number of messages to return

Returns:
    List of Message objects

### `async get_channel_history(channel, limit)`
- 위치: 줄 290
- 설명: Get recent messages in a channel.

Args:
    channel: Channel ID
    limit: Maximum number of messages to return

Returns:
    List of Message objects

### `async open_dm(user_id)`
- 위치: 줄 307
- 설명: Open a DM channel with a user.

Args:
    user_id: User ID

Returns:
    DM channel ID or None if failed
