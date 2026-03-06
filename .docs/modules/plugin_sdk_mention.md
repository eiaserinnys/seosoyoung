# plugin_sdk/mention.py

> 경로: `seosoyoung/plugin_sdk/mention.py`

## 개요

Mention tracking API for plugins.

Provides an interface for plugins to check whether a thread is being
handled by the mention handler, preventing duplicate interventions.
The actual implementation is injected by the host at runtime.

Usage:
    from seosoyoung.plugin_sdk import mention

    # Check if a thread is already handled
    if mention.is_handled(thread_ts):
        return  # skip intervention

    # Mark a thread as being handled
    mention.mark(thread_ts)

## 클래스

### `MentionTrackingBackend` (Protocol)
- 위치: 줄 28
- 설명: Protocol for mention tracking backend implementation.

The host provides an implementation of this protocol.

#### 메서드

- `mark(self, thread_ts)` (줄 34): Register a thread as being handled by mention handler.
- `is_handled(self, thread_ts)` (줄 38): Check whether a thread is currently handled by mention handler.
- `unmark(self, thread_ts)` (줄 42): Remove a thread from tracking.

## 함수

### `set_backend(backend)`
- 위치: 줄 54
- 설명: Set the mention tracking backend implementation.

Called by the host during startup to provide the actual implementation.

### `get_backend()`
- 위치: 줄 63
- 설명: Get the current mention tracking backend.

### `_require_backend()`
- 위치: 줄 68
- 설명: Get backend or raise if not set.

### `mark(thread_ts)`
- 위치: 줄 83
- 설명: Mark a thread as being handled by the mention handler.

Args:
    thread_ts: Thread timestamp to mark

### `is_handled(thread_ts)`
- 위치: 줄 92
- 설명: Check if a thread is currently being handled by mention handler.

Args:
    thread_ts: Thread timestamp to check

Returns:
    True if the thread is being handled, False otherwise

### `unmark(thread_ts)`
- 위치: 줄 104
- 설명: Remove a thread from mention tracking.

Args:
    thread_ts: Thread timestamp to unmark
