# core/context.py

> 경로: `seosoyoung/core/context.py`

## 개요

Hook context factory.

Provides a convenience function for creating HookContext instances.

## 함수

### `create_hook_context(hook_name)`
- 위치: 줄 13
- 설명: Create a HookContext with the given hook name and keyword arguments.

Example::

    ctx = create_hook_context("on_message", text="hello", user="U123")
    # ctx.hook_name == "on_message"
    # ctx.args == {"text": "hello", "user": "U123"}

## 내부 의존성

- `seosoyoung.core.hooks.HookContext`
