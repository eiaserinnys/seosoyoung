"""Tests for core/plugin_manager.py — PluginManager lifecycle and dispatch."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
import types
from typing import Any
from unittest.mock import AsyncMock

import pytest

from seosoyoung.core.context import create_hook_context
from seosoyoung.core.hooks import HookContext, HookPriority, HookResult
from seosoyoung.core.plugin import Plugin, PluginMeta
from seosoyoung.core.plugin_manager import PluginManager


# -- Test fixtures: sample plugin modules ------------------------------------


class GreeterPlugin(Plugin):
    meta = PluginMeta(name="greeter", version="1.0.0", description="Says hello")

    async def on_load(self, config: dict[str, Any]) -> None:
        self.greeting = config["greeting"]

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            return HookResult.CONTINUE, f"{self.greeting} {ctx.args.get('user', '')}"

        return {"on_message": on_message}


class StopperPlugin(Plugin):
    meta = PluginMeta(name="stopper", version="0.1.0")

    async def on_load(self, config: dict[str, Any]) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            return HookResult.STOP, "stopped"

        return {"on_message": on_message}


class SkipperPlugin(Plugin):
    meta = PluginMeta(name="skipper", version="0.1.0")

    async def on_load(self, config: dict[str, Any]) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            return HookResult.SKIP, "should not appear"

        return {"on_message": on_message}


class ErrorPlugin(Plugin):
    meta = PluginMeta(name="error", version="0.1.0")

    async def on_load(self, config: dict[str, Any]) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            raise RuntimeError("handler exploded")

        return {"on_message": on_message}


class FailOnLoadPlugin(Plugin):
    meta = PluginMeta(name="fail_on_load", version="0.1.0")

    async def on_load(self, config: dict[str, Any]) -> None:
        raise RuntimeError("on_load failed")

    async def on_unload(self) -> None:
        pass


class FailOnUnloadPlugin(Plugin):
    meta = PluginMeta(name="fail_on_unload", version="0.1.0")

    async def on_load(self, config: dict[str, Any]) -> None:
        pass

    async def on_unload(self) -> None:
        raise RuntimeError("on_unload failed")


# -- Fake module import infrastructure ----------------------------------------
# PluginManager._cleanup_module removes modules from sys.modules.
# For reload to work in tests, we need a meta_path finder that can
# re-create fake modules on demand after cleanup.

_fake_registry: dict[str, type[Plugin]] = {}


class _FakePluginLoader(importlib.abc.Loader):
    """Loader that populates fake plugin modules from the registry."""

    def create_module(self, spec):
        return None  # Use default module creation

    def exec_module(self, module):
        name = module.__name__
        if name == "fake_plugins":
            module.__path__ = []
            return
        plugin_cls = _fake_registry[name]
        module.__dict__[plugin_cls.__name__] = plugin_cls
        module.__dict__["Plugin"] = Plugin


class _FakePluginFinder(importlib.abc.MetaPathFinder):
    """Meta-path finder that creates fake plugin modules on demand."""

    _loader = _FakePluginLoader()

    def find_spec(self, fullname, path, target=None):
        if fullname == "fake_plugins":
            return importlib.machinery.ModuleSpec(
                fullname, self._loader, is_package=True
            )
        if fullname in _fake_registry:
            return importlib.machinery.ModuleSpec(fullname, self._loader)
        return None


_finder = _FakePluginFinder()


def _inject_module(name: str, plugin_cls: type[Plugin]) -> None:
    """Register a fake plugin module that survives sys.modules cleanup."""
    _fake_registry[name] = plugin_cls
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    # Pre-populate parent package
    if "fake_plugins" not in sys.modules:
        pkg = types.ModuleType("fake_plugins")
        pkg.__path__ = []
        sys.modules["fake_plugins"] = pkg
    # Pre-populate the module itself
    mod = types.ModuleType(name)
    mod.__dict__[plugin_cls.__name__] = plugin_cls
    mod.__dict__["Plugin"] = Plugin
    sys.modules[name] = mod


def _remove_module(name: str) -> None:
    """Clean up a fake module from both registry and sys.modules."""
    _fake_registry.pop(name, None)
    to_remove = [k for k in sys.modules if k == name or k.startswith(name + ".")]
    for k in to_remove:
        del sys.modules[k]


@pytest.fixture()
def notifier():
    return AsyncMock()


@pytest.fixture()
def manager(notifier):
    return PluginManager(notifier=notifier)


@pytest.fixture(autouse=True)
def _cleanup_fake_modules():
    """Ensure fake modules and registry are cleaned up after each test."""
    yield
    _fake_registry.clear()
    for name in list(sys.modules):
        if name.startswith("fake_plugins"):
            del sys.modules[name]
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)


# -- Load tests ---------------------------------------------------------------


class TestLoad:
    async def test_load_success(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        plugin = await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        assert plugin.meta.name == "greeter"
        assert "greeter" in manager.plugins
        notifier.assert_awaited()
        assert "loaded" in notifier.call_args[0][0].lower()

    async def test_load_with_config(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        plugin = await manager.load(
            "fake_plugins.greeter", config={"greeting": "hola"}
        )
        assert plugin.greeting == "hola"

    async def test_load_with_priority(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hello"},
            priority=HookPriority.HIGH,
        )
        assert manager._priorities["greeter"] == HookPriority.HIGH

    async def test_load_missing_dependency(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        with pytest.raises(ValueError, match="Missing dependencies"):
            await manager.load(
                "fake_plugins.greeter", depends_on=["nonexistent"]
            )

    async def test_load_satisfied_dependency(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        _inject_module("fake_plugins.stopper", StopperPlugin)
        await manager.load("fake_plugins.stopper")
        plugin = await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hello"},
            depends_on=["stopper"],
        )
        assert plugin.meta.name == "greeter"

    async def test_load_bad_module(self, manager, notifier):
        with pytest.raises(ModuleNotFoundError):
            await manager.load("fake_plugins.nonexistent_module_xyz")
        assert "failed" in notifier.call_args[0][0].lower()

    async def test_load_no_plugin_class(self, manager, notifier):
        mod = types.ModuleType("fake_plugins.empty")
        sys.modules["fake_plugins.empty"] = mod
        with pytest.raises(TypeError, match="No Plugin subclass"):
            await manager.load("fake_plugins.empty")
        assert "fake_plugins.empty" not in sys.modules

    async def test_load_on_load_failure(self, manager, notifier):
        _inject_module("fake_plugins.fail_on_load", FailOnLoadPlugin)
        with pytest.raises(RuntimeError, match="on_load failed"):
            await manager.load("fake_plugins.fail_on_load")
        assert "fail_on_load" not in manager.plugins
        assert "failed" in notifier.call_args[0][0].lower()

    async def test_load_replaces_existing(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        p1 = await manager.load(
            "fake_plugins.greeter", config={"greeting": "hi"}
        )
        assert p1.greeting == "hi"

        _inject_module("fake_plugins.greeter", GreeterPlugin)
        p2 = await manager.load(
            "fake_plugins.greeter", config={"greeting": "bye"}
        )
        assert p2.greeting == "bye"
        assert manager.plugins["greeter"] is p2


# -- Unload tests -------------------------------------------------------------


class TestUnload:
    async def test_unload_success(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        notifier.reset_mock()

        await manager.unload("greeter")
        assert "greeter" not in manager.plugins
        assert "unloaded" in notifier.call_args[0][0].lower()

    async def test_unload_nonexistent(self, manager):
        with pytest.raises(KeyError, match="Plugin not loaded"):
            await manager.unload("nonexistent")

    async def test_unload_on_unload_failure(self, manager):
        _inject_module("fake_plugins.fail_on_unload", FailOnUnloadPlugin)
        await manager.load("fake_plugins.fail_on_unload")
        # Should not raise, just log a warning
        await manager.unload("fail_on_unload")
        assert "fail_on_unload" not in manager.plugins

    async def test_unload_removes_hooks(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        assert "on_message" in manager._hook_handlers

        await manager.unload("greeter")
        assert "on_message" not in manager._hook_handlers


# -- Reload tests -------------------------------------------------------------


class TestReload:
    async def test_reload_success(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hi"},
            priority=HookPriority.HIGH,
        )
        notifier.reset_mock()

        _inject_module("fake_plugins.greeter", GreeterPlugin)
        plugin = await manager.reload("greeter")
        assert plugin.meta.name == "greeter"
        assert plugin.greeting == "hi"
        assert manager._priorities["greeter"] == HookPriority.HIGH

        # Only one notification: reload, not load+unload
        assert notifier.await_count == 1
        assert "reloaded" in notifier.call_args[0][0].lower()

    async def test_reload_nonexistent(self, manager):
        with pytest.raises(KeyError, match="Plugin not loaded"):
            await manager.reload("nonexistent")

    async def test_reload_failure_notifies(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        notifier.reset_mock()

        # Remove the module so reload fails at import
        _remove_module("fake_plugins.greeter")
        with pytest.raises(ModuleNotFoundError):
            await manager.reload("greeter")

        assert "failed" in notifier.call_args[0][0].lower()


# -- Dispatch tests -----------------------------------------------------------


class TestDispatch:
    async def test_dispatch_continue(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})

        ctx = create_hook_context("on_message", user="Alice")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["hello Alice"]
        assert not result.stopped

    async def test_dispatch_stop(self, manager):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        _inject_module("fake_plugins.stopper", StopperPlugin)

        await manager.load(
            "fake_plugins.stopper", priority=HookPriority.HIGH
        )
        await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hello"},
            priority=HookPriority.LOW,
        )

        ctx = create_hook_context("on_message", user="Bob")
        result = await manager.dispatch("on_message", ctx)
        assert result.stopped
        assert result.results == ["stopped"]

    async def test_dispatch_skip(self, manager):
        _inject_module("fake_plugins.skipper", SkipperPlugin)
        _inject_module("fake_plugins.greeter", GreeterPlugin)

        await manager.load(
            "fake_plugins.skipper", priority=HookPriority.HIGH
        )
        await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hello"},
            priority=HookPriority.LOW,
        )

        ctx = create_hook_context("on_message", user="Carol")
        result = await manager.dispatch("on_message", ctx)
        assert "should not appear" not in result.results
        assert result.results == ["hello Carol"]

    async def test_dispatch_handler_error_continues(self, manager):
        _inject_module("fake_plugins.error", ErrorPlugin)
        _inject_module("fake_plugins.greeter", GreeterPlugin)

        await manager.load(
            "fake_plugins.error", priority=HookPriority.HIGH
        )
        await manager.load(
            "fake_plugins.greeter",
            config={"greeting": "hello"},
            priority=HookPriority.LOW,
        )

        ctx = create_hook_context("on_message", user="Dave")
        result = await manager.dispatch("on_message", ctx)
        # Error plugin's result is skipped, greeter still runs
        assert result.results == ["hello Dave"]
        assert not result.stopped

    async def test_dispatch_unknown_hook(self, manager):
        ctx = create_hook_context("unknown_hook")
        result = await manager.dispatch("unknown_hook", ctx)
        assert result.results == []

    async def test_dispatch_priority_order(self, manager):
        """Higher priority handlers execute first."""

        class LowPlugin(Plugin):
            meta = PluginMeta(name="low", version="0.1.0")
            async def on_load(self, config): pass
            async def on_unload(self): pass
            def register_hooks(self):
                async def h(ctx):
                    return HookResult.CONTINUE, "low"
                return {"test": h}

        class HighPlugin(Plugin):
            meta = PluginMeta(name="high", version="0.1.0")
            async def on_load(self, config): pass
            async def on_unload(self): pass
            def register_hooks(self):
                async def h(ctx):
                    return HookResult.CONTINUE, "high"
                return {"test": h}

        _inject_module("fake_plugins.low", LowPlugin)
        _inject_module("fake_plugins.high", HighPlugin)

        await manager.load("fake_plugins.low", priority=HookPriority.LOW)
        await manager.load("fake_plugins.high", priority=HookPriority.HIGH)

        ctx = create_hook_context("test")
        result = await manager.dispatch("test", ctx)
        assert result.results == ["high", "low"]


# -- sys.modules cleanup tests ------------------------------------------------


class TestModuleCleanup:
    async def test_cleanup_on_unload(self, manager):
        module_name = "fake_plugins.greeter_cleanup"
        _inject_module(module_name, GreeterPlugin)
        await manager.load(module_name, config={"greeting": "hello"})
        assert module_name in sys.modules

        await manager.unload("greeter")
        assert module_name not in sys.modules

    async def test_cleanup_on_load_failure(self, manager):
        module_name = "fake_plugins.fail_cleanup"
        _inject_module(module_name, FailOnLoadPlugin)
        with pytest.raises(RuntimeError):
            await manager.load(module_name)
        assert module_name not in sys.modules

    async def test_cleanup_submodules(self, manager):
        module_name = "fake_plugins.parent"
        sub_name = "fake_plugins.parent.child"

        _inject_module(module_name, GreeterPlugin)
        sys.modules[sub_name] = types.ModuleType(sub_name)

        await manager.load(module_name, config={"greeting": "hello"})
        await manager.unload("greeter")

        assert module_name not in sys.modules
        assert sub_name not in sys.modules


# -- Notification tests -------------------------------------------------------


class TestNotifications:
    async def test_load_notifies(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        notifier.assert_awaited_once()
        msg = notifier.call_args[0][0]
        assert "greeter" in msg

    async def test_unload_notifies(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        notifier.reset_mock()

        await manager.unload("greeter")
        notifier.assert_awaited_once()
        msg = notifier.call_args[0][0]
        assert "unloaded" in msg.lower()

    async def test_no_notifier_no_error(self):
        mgr = PluginManager(notifier=None)
        _inject_module("fake_plugins.greeter_no_notify", GreeterPlugin)
        plugin = await mgr.load(
            "fake_plugins.greeter_no_notify", config={"greeting": "hello"}
        )
        assert plugin.meta.name == "greeter"
        await mgr.unload("greeter")

    async def test_notifier_failure_does_not_raise(self):
        broken_notifier = AsyncMock(side_effect=RuntimeError("slack down"))
        mgr = PluginManager(notifier=broken_notifier)
        _inject_module("fake_plugins.greeter_broken", GreeterPlugin)
        # Should not raise even though notifier fails
        plugin = await mgr.load(
            "fake_plugins.greeter_broken", config={"greeting": "hello"}
        )
        assert plugin.meta.name == "greeter"

    async def test_startup_summary(self, manager, notifier):
        _inject_module("fake_plugins.greeter", GreeterPlugin)
        _inject_module("fake_plugins.stopper", StopperPlugin)
        await manager.load("fake_plugins.greeter", config={"greeting": "hello"})
        await manager.load("fake_plugins.stopper")
        notifier.reset_mock()

        await manager.notify_startup_summary()
        notifier.assert_awaited_once()
        msg = notifier.call_args[0][0]
        assert "greeter" in msg
        assert "stopper" in msg

    async def test_startup_summary_empty(self, manager, notifier):
        await manager.notify_startup_summary()
        notifier.assert_awaited_once()
        assert "No plugins" in notifier.call_args[0][0]
