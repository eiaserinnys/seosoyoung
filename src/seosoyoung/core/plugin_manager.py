"""Plugin lifecycle manager.

Handles loading, unloading, reloading of plugins and dispatching
hook chains. Priority and dependencies are explicit load() parameters.

Notification is delegated to an async callable injected at construction.
The manager does not know about Slack — it only calls the notifier.
"""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Awaitable, Callable

from seosoyoung.core.hooks import HookContext, HookPriority, HookResult
from seosoyoung.core.plugin import Plugin

logger = logging.getLogger(__name__)

Notifier = Callable[[str], Awaitable[None]]


class PluginManager:
    """Manages plugin lifecycle and hook dispatch.

    Priority and dependencies are explicit ``load()`` parameters,
    not buried in plugin config dicts.
    """

    def __init__(self, notifier: Notifier | None = None) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._priorities: dict[str, int] = {}
        self._modules: dict[str, str] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._depends: dict[str, list[str]] = {}
        self._hook_handlers: dict[str, list[tuple[int, str, Any]]] = {}
        self._notifier = notifier

    @property
    def plugins(self) -> dict[str, Plugin]:
        """Snapshot of currently loaded plugins."""
        return dict(self._plugins)

    async def load(
        self,
        module: str,
        config: dict[str, Any] | None = None,
        priority: int = HookPriority.NORMAL,
        depends_on: list[str] | None = None,
    ) -> Plugin:
        """Load a plugin from a dotted module path.

        Args:
            module: Dotted import path (e.g. ``mypackage.plugins.greeter``).
            config: Configuration dict passed to ``plugin.on_load()``.
            priority: Hook execution priority. Higher executes first.
            depends_on: Plugin names that must already be loaded.

        Returns:
            The loaded Plugin instance.

        Raises:
            ValueError: If required dependencies are not loaded.
            TypeError: If the module contains no Plugin subclass.
        """
        config = config if config is not None else {}
        depends_on = depends_on if depends_on is not None else []

        missing = [dep for dep in depends_on if dep not in self._plugins]
        if missing:
            raise ValueError(
                f"Missing dependencies for module '{module}': {missing}"
            )

        try:
            mod = importlib.import_module(module)
        except Exception:
            self._cleanup_module(module)
            await self._notify(f"❌ Plugin load failed (import): `{module}`")
            raise

        plugin_cls = self._find_plugin_class(mod)
        if plugin_cls is None:
            self._cleanup_module(module)
            await self._notify(
                f"❌ Plugin load failed (no Plugin subclass): `{module}`"
            )
            raise TypeError(f"No Plugin subclass found in module '{module}'")

        try:
            plugin = plugin_cls()
            await plugin.on_load(config)
        except Exception:
            self._cleanup_module(module)
            await self._notify(f"❌ Plugin load failed (on_load): `{module}`")
            raise

        name = plugin.meta.name

        if name in self._plugins:
            await self.unload(name)

        self._plugins[name] = plugin
        self._priorities[name] = priority
        self._modules[name] = module
        self._configs[name] = config
        self._depends[name] = depends_on

        hooks = plugin.register_hooks()
        for hook_name, handler in hooks.items():
            if hook_name not in self._hook_handlers:
                self._hook_handlers[hook_name] = []
            self._hook_handlers[hook_name].append((priority, name, handler))
            self._hook_handlers[hook_name].sort(
                key=lambda x: x[0], reverse=True
            )

        await self._notify(
            f"✅ Plugin loaded: `{name}` v{plugin.meta.version}"
        )
        logger.info(
            "Plugin loaded: %s v%s (priority=%d)",
            name,
            plugin.meta.version,
            priority,
        )
        return plugin

    async def unload(self, name: str) -> None:
        """Unload a plugin by name.

        Calls ``on_unload()``, removes hook handlers, and cleans up
        the module from ``sys.modules``.

        Raises:
            KeyError: If the plugin is not loaded.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin not loaded: '{name}'")

        plugin = self._plugins[name]
        module_path = self._modules[name]

        try:
            await plugin.on_unload()
        except Exception:
            logger.warning(
                "Error during on_unload for plugin %s", name, exc_info=True
            )

        for hook_name in list(self._hook_handlers):
            self._hook_handlers[hook_name] = [
                (p, n, h)
                for p, n, h in self._hook_handlers[hook_name]
                if n != name
            ]
            if not self._hook_handlers[hook_name]:
                del self._hook_handlers[hook_name]

        del self._plugins[name]
        del self._priorities[name]
        del self._modules[name]
        del self._configs[name]
        del self._depends[name]

        self._cleanup_module(module_path)

        await self._notify(f"🔌 Plugin unloaded: `{name}`")
        logger.info("Plugin unloaded: %s", name)

    async def reload(self, name: str) -> Plugin:
        """Reload a plugin, preserving config, priority, and dependencies.

        Internally unloads and re-loads the plugin. Only one notification
        is sent (reload success or failure), not the individual
        unload/load notifications.

        Raises:
            KeyError: If the plugin is not loaded.
        """
        if name not in self._plugins:
            raise KeyError(f"Plugin not loaded: '{name}'")

        module_path = self._modules[name]
        config = self._configs[name]
        priority = self._priorities[name]
        depends_on = self._depends[name]

        saved_notifier = self._notifier
        self._notifier = None
        try:
            await self.unload(name)
            plugin = await self.load(module_path, config, priority, depends_on)
        except Exception:
            self._notifier = saved_notifier
            await self._notify(
                f"❌ Plugin reload failed: `{name}` (`{module_path}`)"
            )
            raise
        self._notifier = saved_notifier

        await self._notify(
            f"🔄 Plugin reloaded: `{name}` v{plugin.meta.version}"
        )
        logger.info("Plugin reloaded: %s", name)
        return plugin

    async def dispatch(self, hook_name: str, context: HookContext) -> HookContext:
        """Dispatch a hook through registered handlers in priority order.

        Each handler returns ``(HookResult, value)``:
          - CONTINUE: append value, call next handler.
          - STOP: append value, halt the chain.
          - SKIP: discard value, call next handler.

        Handler exceptions are logged and skipped (do not break the chain).
        """
        handlers = self._hook_handlers.get(hook_name, [])

        for _priority, plugin_name, handler in handlers:
            if context.stopped:
                break

            try:
                result, value = await handler(context)
            except Exception:
                logger.error(
                    "Hook handler error: hook=%s plugin=%s",
                    hook_name,
                    plugin_name,
                    exc_info=True,
                )
                continue

            if result == HookResult.CONTINUE:
                context.results.append(value)
            elif result == HookResult.STOP:
                context.results.append(value)
                context.stopped = True
            # HookResult.SKIP: do nothing

        return context

    async def notify_startup_summary(self) -> None:
        """Send a summary of all loaded plugins."""
        if not self._plugins:
            await self._notify("📦 No plugins loaded.")
            return

        lines = ["📦 Plugin startup summary:"]
        for name, plugin in self._plugins.items():
            priority = self._priorities[name]
            lines.append(
                f"  - `{name}` v{plugin.meta.version} (priority={priority})"
            )
        await self._notify("\n".join(lines))

    async def _notify(self, message: str) -> None:
        """Send a notification if a notifier is configured."""
        if self._notifier is None:
            return
        try:
            await self._notifier(message)
        except Exception:
            logger.warning(
                "Failed to send plugin notification: %s",
                message,
                exc_info=True,
            )

    @staticmethod
    def _find_plugin_class(mod: Any) -> type[Plugin] | None:
        """Find the single Plugin subclass in a module.

        Each plugin module must define exactly one Plugin subclass.
        Raises TypeError if multiple are found.
        """
        candidates = [
            getattr(mod, name)
            for name in dir(mod)
            if (
                isinstance(getattr(mod, name), type)
                and issubclass(getattr(mod, name), Plugin)
                and getattr(mod, name) is not Plugin
            )
        ]
        if len(candidates) > 1:
            names = [c.__name__ for c in candidates]
            raise TypeError(
                f"Module contains multiple Plugin subclasses: {names}. "
                f"Each module must define exactly one."
            )
        return candidates[0] if candidates else None

    @staticmethod
    def _cleanup_module(module_path: str) -> None:
        """Remove a module and its submodules from sys.modules."""
        to_remove = [
            key
            for key in sys.modules
            if key == module_path or key.startswith(module_path + ".")
        ]
        for key in to_remove:
            del sys.modules[key]
