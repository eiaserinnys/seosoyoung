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
- 위치: 줄 53
- 설명: Slack backend implementation using slack_sdk client.

#### 메서드

- `__init__(self, client)` (줄 56): Initialize with Slack WebClient.
- `async send_message(self, channel, text, thread_ts)` (줄 64): Send a message to a channel.
- `async update_message(self, channel, ts, text)` (줄 88): Update an existing message.
- `async add_reaction(self, channel, ts, emoji)` (줄 112): Add a reaction to a message.
- `async remove_reaction(self, channel, ts, emoji)` (줄 133): Remove a reaction from a message.
- `async get_user_info(self, user_id)` (줄 154): Get information about a user.
- `async get_thread_replies(self, channel, thread_ts, limit)` (줄 171): Get replies in a thread.
- `async get_channel_history(self, channel, limit)` (줄 200): Get recent messages in a channel.
- `async open_dm(self, user_id)` (줄 227): Open a DM channel with a user.

### `SoulstreamBackendImpl` (SoulstreamBackend)
- 위치: 줄 242
- 설명: Soulstream backend implementation using ClaudeExecutor.

#### 메서드

- `__init__(self, executor, session_manager, restart_manager, data_dir, slack_client, update_message_fn)` (줄 245): Initialize with Claude executor and session manager.
- `_build_presentation(self, channel, thread_ts, msg_ts, session_id, role)` (줄 272): presentation이 전달되지 않은 호출(워처 등)을 위해 PresentationContext를 자동 구성.
- `async run(self, prompt, channel, thread_ts, role, session_id, on_progress, on_compact)` (줄 323): Execute Claude Code with the given prompt.
- `async compact(self, session_id)` (줄 440): Compact a Claude Code session.
- `get_session_id(self, thread_ts)` (줄 462): Get the Claude Code session ID for a thread.
- `is_restart_pending(self)` (줄 467): Check if a restart is pending.
- `get_data_dir(self)` (줄 471): Get the data directory for plugin storage.

### `MentionTrackingBackendImpl`
- 위치: 줄 481
- 설명: Mention tracking backend wrapping the existing MentionTracker.

#### 메서드

- `__init__(self, tracker)` (줄 484): 
- `mark(self, thread_ts)` (줄 487): 
- `is_handled(self, thread_ts)` (줄 490): 
- `unmark(self, thread_ts)` (줄 493): 

## 함수

### `async _noop_progress(_msg)`
- 위치: 줄 40
- 설명: text_only 모드용 no-op progress 콜백.

### `async _noop_compact(_session_id, _msg)`
- 위치: 줄 44
- 설명: text_only 모드용 no-op compact 콜백.

### `init_plugin_backends(slack_client, executor, session_manager, restart_manager, data_dir, update_message_fn, mention_tracker)`
- 위치: 줄 502
- 설명: Initialize plugin SDK backends.

Call this during startup after slack_client and executor are ready.

Args:
    slack_client: Slack WebClient instance
    executor: ClaudeExecutor instance
    session_manager: SessionManager instance
    restart_manager: RestartManager instance
    data_dir: Data directory for plugin storage
    update_message_fn: (client, channel, ts, text, *, blocks=None) -> None
                       전달하면 워처 등에서 on_progress/on_compact가 자동 생성됨
    mention_tracker: MentionTracker instance for mention tracking backend

## 내부 의존성

- `seosoyoung.plugin_sdk.mention`
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
- `seosoyoung.slackbot.presentation.node_map.SlackNodeMap`
