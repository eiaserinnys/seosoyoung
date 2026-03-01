"""Plugin base class and metadata.

Plugins are self-describing units of functionality. Each plugin declares
its identity via PluginMeta and registers hook handlers.

Priority and dependencies are NOT part of plugin metadata; they belong
to the plugin registry (plugins.yaml) and are passed as explicit
parameters to PluginManager.load().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from seosoyoung.core.hooks import HookContext, HookResult


@dataclass(frozen=True)
class PluginMeta:
    """Immutable plugin identity.

    Contains only name, version, and description.
    No priority, no dependencies — those are registry concerns.
    """

    name: str
    version: str
    description: str = ""


HookHandler = Callable[["HookContext"], Awaitable[tuple["HookResult", Any]]]


class Plugin(ABC):
    """Base class for all plugins.

    Subclasses must:
      - Set ``meta`` as a class attribute or in ``__init__``.
      - Implement ``on_load()`` and ``on_unload()``.
      - Optionally override ``register_hooks()`` to participate in hook chains.
    """

    meta: PluginMeta

    @abstractmethod
    async def on_load(self, config: dict[str, Any]) -> None:
        """Called when the plugin is loaded.

        ``config`` comes from plugins.yaml, not from .env.
        """

    @abstractmethod
    async def on_unload(self) -> None:
        """Called when the plugin is about to be unloaded."""

    def register_hooks(self) -> dict[str, HookHandler]:
        """Return a mapping of hook_name -> async handler.

        Each handler signature: ``async (ctx: HookContext) -> (HookResult, value)``

        Default implementation returns an empty dict (no hooks).
        """
        return {}
