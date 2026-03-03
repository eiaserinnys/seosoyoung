"""Hook system primitives for the plugin architecture.

Defines priority levels, result types, and the context object
that flows through a hook handler chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class HookPriority(IntEnum):
    """Execution priority for hook handlers. Higher values execute first."""

    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class HookResult(Enum):
    """Result of a hook handler, controlling chain behavior.

    CONTINUE: append value to results, call next handler.
    STOP:     append value to results, halt the chain.
    SKIP:     do not append value, call next handler.
    """

    CONTINUE = "continue"
    STOP = "stop"
    SKIP = "skip"


@dataclass
class HookContext:
    """Mutable context passed through a hook handler chain.

    Attributes:
        hook_name: Name of the hook being dispatched.
        args: Keyword arguments passed to the hook.
        results: Accumulated return values from handlers.
        stopped: Set to True when a handler returns STOP.
    """

    hook_name: str
    args: dict[str, Any] = field(default_factory=dict)
    results: list[Any] = field(default_factory=list)
    stopped: bool = False
