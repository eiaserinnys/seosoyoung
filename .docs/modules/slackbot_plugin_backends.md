# slackbot/plugin_backends.py

> 경로: `seosoyoung/slackbot/plugin_backends.py`

## 개요

Plugin SDK backend implementations.

This module provides the actual implementations of plugin_sdk APIs.
Called during startup to inject backends into plugin_sdk modules.

These backends wrap the existing seosoyoung infrastructure
(slack_client, claude executor, session manager, etc.)

## 클래스

### `SlackBackendImpl` (SlackBackend)
- 위치: 줄 43
- 설명: Slack backend implementation using slack_sdk client.

#### 메서드

- `__init__(self, client)` (줄 46): Initialize with Slack WebClient.
- `async send_message(self, channel, text, thread_ts)` (줄 54): Send a message to a channel.
- `async update_message(self, channel, ts, text)` (줄 78): Update an existing message.
- `async add_reaction(self, channel, ts, emoji)` (줄 102): Add a reaction to a message.
- `async remove_reaction(self, channel, ts, emoji)` (줄 123): Remove a reaction from a message.
- `async get_user_info(self, user_id)` (줄 144): Get information about a user.
- `async get_thread_replies(self, channel, thread_ts, limit)` (줄 161): Get replies in a thread.
- `async get_channel_history(self, channel, limit)` (줄 190): Get recent messages in a channel.
- `async open_dm(self, user_id)` (줄 217): Open a DM channel with a user.

### `SoulstreamBackendImpl` (SoulstreamBackend)
- 위치: 줄 232
- 설명: Soulstream backend implementation using ClaudeExecutor.

#### 메서드

- `__init__(self, executor, session_manager, restart_manager, data_dir, slack_client)` (줄 235): Initialize with Claude executor and session manager.
- `_build_presentation(self, channel, thread_ts, msg_ts, session_id, role)` (줄 258): presentation이 전달되지 않은 호출(워처 등)을 위해 PresentationContext를 자동 구성.
- `async run(self, prompt, channel, thread_ts, role, session_id, on_progress, on_compact)` (줄 306): Execute Claude Code with the given prompt.
- `async compact(self, session_id)` (줄 367): Compact a Claude Code session.
- `get_session_id(self, thread_ts)` (줄 389): Get the Claude Code session ID for a thread.
- `is_restart_pending(self)` (줄 394): Check if a restart is pending.
- `get_data_dir(self)` (줄 398): Get the data directory for plugin storage.

## 함수

### `init_plugin_backends(slack_client, executor, session_manager, restart_manager, data_dir)`
- 위치: 줄 408
- 설명: Initialize plugin SDK backends.

Call this during startup after slack_client and executor are ready.

Args:
    slack_client: Slack WebClient instance
    executor: ClaudeExecutor instance
    session_manager: SessionManager instance
    restart_manager: RestartManager instance
    data_dir: Data directory for plugin storage

## 내부 의존성

- `seosoyoung.plugin_sdk.slack`
- `seosoyoung.plugin_sdk.slack.Message`
- `seosoyoung.plugin_sdk.slack.ReactionResult`
- `seosoyoung.plugin_sdk.slack.SendMessageResult`
- `seosoyoung.plugin_sdk.slack.SlackBackend`
- `seosoyoung.plugin_sdk.slack.UserInfo`
- `seosoyoung.plugin_sdk.soulstream`
- `seosoyoung.plugin_sdk.soulstream.CompactResult`
- `seosoyoung.plugin_sdk.soulstream.RunResult`
- `seosoyoung.plugin_sdk.soulstream.RunStatus`
- `seosoyoung.plugin_sdk.soulstream.SoulstreamBackend`
