# plugin_sdk/soulstream.py

> 경로: `seosoyoung/plugin_sdk/soulstream.py`

## 개요

Soulstream API for plugins.

Provides an interface for plugins to request Claude Code execution.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import soulstream

    # Request Claude Code execution
    result = await soulstream.run(
        prompt="Analyze this code...",
        channel="C12345",
        thread_ts="1234567890.123456",
    )

## 클래스

### `RunStatus` (Enum)
- 위치: 줄 30
- 설명: Status of a Soulstream run.

### `RunRequest`
- 위치: 줄 41
- 설명: Request to run Claude Code.

This is what plugins return to request Claude Code execution.
The host handles the actual execution.

### `RunResult`
- 위치: 줄 57
- 설명: Result of a Soulstream run.

### `CompactResult`
- 위치: 줄 68
- 설명: Result of a session compact operation.

### `SoulstreamBackend` (Protocol)
- 위치: 줄 89
- 설명: Protocol for Soulstream backend implementation.

The host provides an implementation of this protocol.

#### 메서드

- `async run(self, prompt, channel, thread_ts, role, session_id, on_progress, on_compact)` (줄 95): Execute Claude Code with the given prompt.
- `async compact(self, session_id)` (줄 123): Compact a Claude Code session to reduce context size.
- `get_session_id(self, thread_ts)` (줄 134): Get the Claude Code session ID for a thread.
- `is_restart_pending(self)` (줄 145): Check if a restart is pending.
- `get_data_dir(self)` (줄 153): Get the data directory for plugin storage.

## 함수

### `set_backend(backend)`
- 위치: 줄 169
- 설명: Set the Soulstream backend implementation.

Called by the host during startup to provide the actual implementation.

### `get_backend()`
- 위치: 줄 178
- 설명: Get the current Soulstream backend.

### `_require_backend()`
- 위치: 줄 183
- 설명: Get backend or raise if not set.

### `async run(prompt, channel, thread_ts, role, session_id, on_progress, on_compact)`
- 위치: 줄 198
- 설명: Execute Claude Code with the given prompt.

This is the main entry point for plugins to run Claude Code.

Args:
    prompt: The prompt to send to Claude Code
    channel: Slack channel ID for output
    thread_ts: Thread timestamp for output
    role: User role (affects permissions)
    session_id: Existing session ID to resume
    on_progress: Callback for progress updates
    on_compact: Callback for compact notifications
    **kwargs: Additional arguments

Returns:
    RunResult with status and output

Example:
    result = await soulstream.run(
        prompt="What files are in this directory?",
        channel="C12345",
        thread_ts="1234567890.123456",
    )
    if result.ok:
        print(f"Session: {result.session_id}")

### `async compact(session_id)`
- 위치: 줄 247
- 설명: Compact a Claude Code session to reduce context size.

Compacting summarizes the conversation history to free up
context window space for longer sessions.

Args:
    session_id: Session ID to compact

Returns:
    CompactResult with new session_id if changed

Example:
    result = await soulstream.compact("session-abc123")
    if result.ok and result.session_id:
        print(f"New session: {result.session_id}")

### `get_session_id(thread_ts)`
- 위치: 줄 268
- 설명: Get the Claude Code session ID for a thread.

Args:
    thread_ts: Thread timestamp

Returns:
    Session ID or None if no session exists

Example:
    session_id = soulstream.get_session_id("1234567890.123456")
    if session_id:
        await soulstream.compact(session_id)

### `is_restart_pending()`
- 위치: 줄 286
- 설명: Check if a system restart is pending.

When a restart is pending, plugins should avoid starting new tasks.

Returns:
    True if restart is pending, False otherwise

Example:
    if soulstream.is_restart_pending():
        await slack.send_message(
            channel=channel,
            text="재시작을 대기하는 중입니다."
        )
        return

### `get_data_dir()`
- 위치: 줄 306
- 설명: Get the data directory for plugin storage.

Returns:
    Path to data directory where plugins can store state files

Example:
    data_dir = soulstream.get_data_dir()
    plugin_dir = data_dir / "my_plugin"
    plugin_dir.mkdir(exist_ok=True)

### `create_request(prompt, channel, thread_ts, role, session_id)`
- 위치: 줄 326
- 설명: Create a RunRequest for hook-based execution.

Some hooks may need to return a request object instead of
directly calling run(). This helper creates the request.

Args:
    prompt: The prompt to send
    channel: Slack channel ID
    thread_ts: Thread timestamp
    role: User role
    session_id: Existing session ID
    **metadata: Additional metadata

Returns:
    RunRequest object

Example:
    async def _on_reaction(self, ctx: HookContext):
        request = soulstream.create_request(
            prompt="Execute this task...",
            channel=ctx.args["channel"],
            thread_ts=ctx.args["thread_ts"],
        )
        ctx.args["soulstream_request"] = request
        return HookResult.CONTINUE, request
