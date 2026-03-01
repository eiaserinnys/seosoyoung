# core/hooks.py

> 경로: `seosoyoung/core/hooks.py`

## 개요

Hook system primitives for the plugin architecture.

Defines priority levels, result types, and the context object
that flows through a hook handler chain.

## 클래스

### `HookPriority` (IntEnum)
- 위치: 줄 14
- 설명: Execution priority for hook handlers. Higher values execute first.

### `HookResult` (Enum)
- 위치: 줄 23
- 설명: Result of a hook handler, controlling chain behavior.

CONTINUE: append value to results, call next handler.
STOP:     append value to results, halt the chain.
SKIP:     do not append value, call next handler.

### `HookContext`
- 위치: 줄 37
- 설명: Mutable context passed through a hook handler chain.

Attributes:
    hook_name: Name of the hook being dispatched.
    args: Keyword arguments passed to the hook.
    results: Accumulated return values from handlers.
    stopped: Set to True when a handler returns STOP.
