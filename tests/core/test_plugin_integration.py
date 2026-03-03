"""Integration tests for the plugin system.

Tests the end-to-end flow: YAML registry → config loading → plugin lifecycle
→ hook dispatch → reload → unload. Uses temporary YAML files and fake plugin
modules to verify the full pipeline without touching real Slack or external APIs.

Marked with ``@pytest.mark.integration`` — run with ``pytest -m integration``.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import yaml

from seosoyoung.core.context import create_hook_context
from seosoyoung.core.hooks import HookContext, HookPriority, HookResult
from seosoyoung.core.plugin import Plugin, PluginMeta
from seosoyoung.core.plugin_config import load_plugin_config, load_plugin_registry
from seosoyoung.core.plugin_manager import PluginManager


# -- Fake plugin definitions --------------------------------------------------


class AlphaPlugin(Plugin):
    """Records lifecycle events for verification."""

    meta = PluginMeta(name="alpha", version="1.0.0", description="Alpha plugin")

    async def on_load(self, config: dict[str, Any]) -> None:
        self.loaded_config = config
        self.events: list[str] = ["loaded"]

    async def on_unload(self) -> None:
        self.events.append("unloaded")

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            text = ctx.args.get("text", "")
            return HookResult.CONTINUE, f"alpha:{text}"

        async def on_startup(ctx: HookContext) -> tuple[HookResult, Any]:
            self.events.append("startup")
            return HookResult.CONTINUE, {"alpha_ref": "alpha_started"}

        return {"on_message": on_message, "on_startup": on_startup}


class BetaPlugin(Plugin):
    """Depends on alpha, transforms messages."""

    meta = PluginMeta(name="beta", version="2.0.0", description="Beta plugin")

    async def on_load(self, config: dict[str, Any]) -> None:
        self.prefix = config["prefix"]

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            text = ctx.args.get("text", "")
            return HookResult.CONTINUE, f"{self.prefix}:{text}"

        return {"on_message": on_message}


class GammaPlugin(Plugin):
    """Stops the hook chain (gate keeper)."""

    meta = PluginMeta(name="gamma", version="0.5.0", description="Gate keeper")

    async def on_load(self, config: dict[str, Any]) -> None:
        self.block_keyword = config.get("block_keyword", "blocked")

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            text = ctx.args.get("text", "")
            if self.block_keyword in text:
                return HookResult.STOP, "gate_closed"
            return HookResult.SKIP, None

        return {"on_message": on_message}


class BrokenPlugin(Plugin):
    """Always raises on hook dispatch."""

    meta = PluginMeta(name="broken", version="0.0.1")

    async def on_load(self, config: dict[str, Any]) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    def register_hooks(self) -> dict:
        async def on_message(ctx: HookContext) -> tuple[HookResult, Any]:
            raise RuntimeError("broken handler exploded")

        return {"on_message": on_message}


class LoadFailPlugin(Plugin):
    """Fails during on_load."""

    meta = PluginMeta(name="load_fail", version="0.0.1")

    async def on_load(self, config: dict[str, Any]) -> None:
        raise ValueError("config is invalid")

    async def on_unload(self) -> None:
        pass


# -- Fake module infrastructure -----------------------------------------------

_integration_registry: dict[str, type[Plugin]] = {}


class _IntegrationLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__
        if name == "integration_plugins":
            module.__path__ = []
            return
        plugin_cls = _integration_registry[name]
        module.__dict__[plugin_cls.__name__] = plugin_cls
        module.__dict__["Plugin"] = Plugin


class _IntegrationFinder(importlib.abc.MetaPathFinder):
    _loader = _IntegrationLoader()

    def find_spec(self, fullname, path, target=None):
        if fullname == "integration_plugins":
            return importlib.machinery.ModuleSpec(
                fullname, self._loader, is_package=True
            )
        if fullname in _integration_registry:
            return importlib.machinery.ModuleSpec(fullname, self._loader)
        return None


_finder = _IntegrationFinder()


def _register_plugin(name: str, cls: type[Plugin]) -> None:
    _integration_registry[name] = cls
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    if "integration_plugins" not in sys.modules:
        pkg = types.ModuleType("integration_plugins")
        pkg.__path__ = []
        sys.modules["integration_plugins"] = pkg
    mod = types.ModuleType(name)
    mod.__dict__[cls.__name__] = cls
    mod.__dict__["Plugin"] = Plugin
    sys.modules[name] = mod


@pytest.fixture(autouse=True)
def _cleanup_integration_modules():
    yield
    _integration_registry.clear()
    for name in list(sys.modules):
        if name.startswith("integration_plugins"):
            del sys.modules[name]
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)


# -- YAML helper fixtures ----------------------------------------------------


@pytest.fixture()
def plugins_dir(tmp_path):
    """Create a temporary plugins/ directory with YAML files."""
    d = tmp_path / "plugins"
    d.mkdir()
    return d


@pytest.fixture()
def write_yaml(plugins_dir):
    """Write YAML content to the plugins directory."""

    def _write(filename: str, content: Any) -> Path:
        p = plugins_dir / filename
        p.write_text(yaml.dump(content), encoding="utf-8")
        return p

    return _write


@pytest.fixture()
def notifier():
    return AsyncMock()


@pytest.fixture()
def manager(notifier):
    return PluginManager(notifier=notifier)


# -- Integration tests --------------------------------------------------------

pytestmark = pytest.mark.integration


class TestRegistryToLoadLifecycle:
    """YAML 레지스트리 → config 로드 → 플러그인 로드 end-to-end."""

    async def test_load_from_registry_and_config(
        self, manager, write_yaml, plugins_dir
    ):
        """plugins.yaml + alpha.yaml → 플러그인 로드 성공."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        registry = [
            {
                "name": "alpha",
                "module": "integration_plugins.alpha",
                "priority": 100,
                "config": "plugins/alpha.yaml",
                "enabled": True,
            }
        ]
        registry_path = write_yaml("plugins.yaml", registry)

        alpha_config = {"greeting": "hello", "max_retries": 3}
        write_yaml("alpha.yaml", alpha_config)

        entries = load_plugin_registry(registry_path)
        assert len(entries) == 1

        entry = entries[0]
        config_path = plugins_dir / "alpha.yaml"
        config = load_plugin_config(config_path)

        plugin = await manager.load(
            module=entry["module"],
            config=config,
            priority=entry["priority"],
        )

        assert plugin.meta.name == "alpha"
        assert plugin.loaded_config == alpha_config
        assert "alpha" in manager.plugins

    async def test_disabled_plugin_skipped(self, write_yaml, plugins_dir):
        """enabled: false인 항목은 레지스트리에서 필터링."""
        registry = [
            {
                "name": "alpha",
                "module": "integration_plugins.alpha",
                "priority": 50,
                "config": "plugins/alpha.yaml",
                "enabled": False,
            },
            {
                "name": "beta",
                "module": "integration_plugins.beta",
                "priority": 50,
                "config": "plugins/beta.yaml",
                "enabled": True,
            },
        ]
        registry_path = write_yaml("plugins.yaml", registry)
        entries = load_plugin_registry(registry_path)

        assert len(entries) == 1
        assert entries[0]["name"] == "beta"

    async def test_missing_config_file_raises(self, manager, write_yaml, plugins_dir):
        """config YAML 누락 시 FileNotFoundError."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        registry = [
            {
                "name": "alpha",
                "module": "integration_plugins.alpha",
                "priority": 50,
                "config": "plugins/nonexistent.yaml",
            }
        ]
        write_yaml("plugins.yaml", registry)

        with pytest.raises(FileNotFoundError, match="Plugin config not found"):
            load_plugin_config(plugins_dir / "nonexistent.yaml")


class TestMultiPluginDispatch:
    """여러 플러그인이 로드된 상태에서 훅 디스패치 검증."""

    async def test_priority_ordered_dispatch(self, manager):
        """높은 우선순위 → 낮은 우선순위 순서로 실행."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.beta", BetaPlugin)

        await manager.load(
            "integration_plugins.alpha",
            config={},
            priority=HookPriority.LOW,
        )
        await manager.load(
            "integration_plugins.beta",
            config={"prefix": "BETA"},
            priority=HookPriority.HIGH,
        )

        ctx = create_hook_context("on_message", text="hello")
        result = await manager.dispatch("on_message", ctx)

        # HIGH(beta) first, then LOW(alpha)
        assert result.results == ["BETA:hello", "alpha:hello"]
        assert not result.stopped

    async def test_gate_keeper_stops_chain(self, manager):
        """STOP 반환 시 후속 핸들러 실행 안 됨."""
        _register_plugin("integration_plugins.gamma", GammaPlugin)
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.gamma",
            config={"block_keyword": "spam"},
            priority=HookPriority.CRITICAL,
        )
        await manager.load(
            "integration_plugins.alpha",
            config={},
            priority=HookPriority.NORMAL,
        )

        ctx = create_hook_context("on_message", text="this is spam")
        result = await manager.dispatch("on_message", ctx)

        assert result.stopped
        assert result.results == ["gate_closed"]

    async def test_gate_keeper_skips_clean_messages(self, manager):
        """SKIP 반환 시 결과에 포함되지 않고 체인 계속."""
        _register_plugin("integration_plugins.gamma", GammaPlugin)
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.gamma",
            config={"block_keyword": "spam"},
            priority=HookPriority.CRITICAL,
        )
        await manager.load(
            "integration_plugins.alpha",
            config={},
            priority=HookPriority.NORMAL,
        )

        ctx = create_hook_context("on_message", text="clean message")
        result = await manager.dispatch("on_message", ctx)

        assert not result.stopped
        assert result.results == ["alpha:clean message"]


class TestErrorIsolation:
    """플러그인 실패가 다른 플러그인에 영향을 주지 않는지 검증."""

    async def test_broken_handler_skipped_others_continue(self, manager):
        """핸들러 예외 발생 시 해당 플러그인만 건너뛰고 다음 실행."""
        _register_plugin("integration_plugins.broken", BrokenPlugin)
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.broken",
            config={},
            priority=HookPriority.HIGH,
        )
        await manager.load(
            "integration_plugins.alpha",
            config={},
            priority=HookPriority.LOW,
        )

        ctx = create_hook_context("on_message", text="test")
        result = await manager.dispatch("on_message", ctx)

        assert result.results == ["alpha:test"]
        assert not result.stopped

    async def test_load_failure_does_not_affect_loaded_plugins(self, manager):
        """한 플러그인 로드 실패가 이미 로드된 플러그인에 영향 없음."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.load_fail", LoadFailPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.NORMAL
        )

        with pytest.raises(ValueError, match="config is invalid"):
            await manager.load(
                "integration_plugins.load_fail",
                config={},
                priority=HookPriority.HIGH,
            )

        # alpha is still loaded and functional
        assert "alpha" in manager.plugins
        assert "load_fail" not in manager.plugins

        ctx = create_hook_context("on_message", text="ok")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["alpha:ok"]


class TestDependencyChain:
    """플러그인 의존성 체인 검증."""

    async def test_dependency_satisfied(self, manager):
        """depends_on에 명시된 플러그인이 이미 로드되어 있으면 성공."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.beta", BetaPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.HIGH
        )
        plugin = await manager.load(
            "integration_plugins.beta",
            config={"prefix": "B"},
            priority=HookPriority.NORMAL,
            depends_on=["alpha"],
        )

        assert plugin.meta.name == "beta"

    async def test_dependency_missing_raises(self, manager):
        """depends_on 플러그인이 미로드 시 ValueError."""
        _register_plugin("integration_plugins.beta", BetaPlugin)

        with pytest.raises(ValueError, match="Missing dependencies"):
            await manager.load(
                "integration_plugins.beta",
                config={"prefix": "B"},
                depends_on=["alpha"],
            )

    async def test_unload_dependency_while_dependent_loaded(self, manager):
        """의존 대상 언로드 시 의존자는 고아가 됨 (현재 동작 문서화)."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.beta", BetaPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.HIGH
        )
        await manager.load(
            "integration_plugins.beta",
            config={"prefix": "B"},
            priority=HookPriority.NORMAL,
            depends_on=["alpha"],
        )

        # 현재 동작: 역방향 의존성 체크 없이 언로드 성공
        await manager.unload("alpha")
        assert "alpha" not in manager.plugins
        assert "beta" in manager.plugins  # beta is orphaned but still functional

        ctx = create_hook_context("on_message", text="orphan")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["B:orphan"]


class TestReloadPreservesState:
    """리로드 시 config, priority, depends_on이 보존되는지 검증."""

    async def test_reload_preserves_config_and_priority(self, manager, notifier):
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.alpha",
            config={"greeting": "preserved"},
            priority=HookPriority.HIGH,
        )
        notifier.reset_mock()

        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        plugin = await manager.reload("alpha")

        assert plugin.loaded_config == {"greeting": "preserved"}
        assert manager._priorities["alpha"] == HookPriority.HIGH

        # Only one notification for reload
        notifier.assert_awaited_once()
        assert "reloaded" in notifier.call_args[0][0].lower()

    async def test_reload_picks_up_new_code(self, manager):
        """리로드 시 새 모듈 코드 반영 확인."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.NORMAL
        )

        ctx = create_hook_context("on_message", text="x")
        r1 = await manager.dispatch("on_message", ctx)
        assert r1.results == ["alpha:x"]

        # Simulate updated module code
        class AlphaPluginV2(Plugin):
            meta = PluginMeta(name="alpha", version="2.0.0", description="Updated")

            async def on_load(self, config):
                self.loaded_config = config
                self.events = ["loaded"]

            async def on_unload(self):
                pass

            def register_hooks(self):
                async def on_message(ctx):
                    return HookResult.CONTINUE, f"alpha_v2:{ctx.args.get('text', '')}"

                return {"on_message": on_message}

        _register_plugin("integration_plugins.alpha", AlphaPluginV2)
        reloaded = await manager.reload("alpha")
        assert reloaded.meta.version == "2.0.0"

        ctx2 = create_hook_context("on_message", text="y")
        r2 = await manager.dispatch("on_message", ctx2)
        assert r2.results == ["alpha_v2:y"]

    async def test_reload_hooks_re_registered(self, manager):
        """리로드 후 훅이 다시 등록되어 디스패치 가능."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.NORMAL
        )

        ctx = create_hook_context("on_message", text="before")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["alpha:before"]

        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        await manager.reload("alpha")

        ctx2 = create_hook_context("on_message", text="after")
        result2 = await manager.dispatch("on_message", ctx2)
        assert result2.results == ["alpha:after"]


class TestStartupHookPipeline:
    """on_startup 훅을 통한 런타임 레퍼런스 전달 검증."""

    async def test_startup_returns_runtime_refs(self, manager):
        """on_startup 훅 결과에서 런타임 레퍼런스를 추출."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.NORMAL
        )

        ctx = create_hook_context(
            "on_startup",
            slack_client="mock_client",
            data_dir="/tmp/data",
        )
        result = await manager.dispatch("on_startup", ctx)

        assert len(result.results) == 1
        assert result.results[0] == {"alpha_ref": "alpha_started"}
        assert not result.stopped

    async def test_startup_multiple_plugins_aggregate(self, manager):
        """여러 플러그인이 on_startup에서 각각 레퍼런스 반환 → 모두 수집."""

        class StartupBeta(Plugin):
            meta = PluginMeta(name="startup_beta", version="1.0.0")

            async def on_load(self, config):
                pass

            async def on_unload(self):
                pass

            def register_hooks(self):
                async def on_startup(ctx):
                    return HookResult.CONTINUE, {"beta_ref": "beta_started"}

                return {"on_startup": on_startup}

        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.startup_beta", StartupBeta)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.HIGH
        )
        await manager.load(
            "integration_plugins.startup_beta",
            config={},
            priority=HookPriority.NORMAL,
        )

        ctx = create_hook_context("on_startup")
        result = await manager.dispatch("on_startup", ctx)

        refs = {}
        for r in result.results:
            if isinstance(r, dict):
                refs.update(r)

        assert refs["alpha_ref"] == "alpha_started"
        assert refs["beta_ref"] == "beta_started"


class TestFullLifecycle:
    """YAML → 로드 → 디스패치 → 언로드 전체 생명주기."""

    async def test_registry_load_dispatch_unload(
        self, manager, notifier, write_yaml, plugins_dir
    ):
        """전체 파이프라인: YAML → config → load → dispatch → unload."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.beta", BetaPlugin)

        registry = [
            {
                "name": "alpha",
                "module": "integration_plugins.alpha",
                "priority": 100,
                "config": "plugins/alpha.yaml",
            },
            {
                "name": "beta",
                "module": "integration_plugins.beta",
                "priority": 50,
                "config": "plugins/beta.yaml",
                "depends_on": ["alpha"],
            },
        ]
        write_yaml("plugins.yaml", registry)
        write_yaml("alpha.yaml", {"greeting": "hi"})
        write_yaml("beta.yaml", {"prefix": "B"})

        # 1) Load from registry
        entries = load_plugin_registry(plugins_dir / "plugins.yaml")
        for entry in entries:
            config = load_plugin_config(plugins_dir / Path(entry["config"]).name)
            await manager.load(
                module=entry["module"],
                config=config,
                priority=entry["priority"],
                depends_on=entry.get("depends_on", []),
            )

        assert len(manager.plugins) == 2

        # 2) Startup summary
        notifier.reset_mock()
        await manager.notify_startup_summary()
        summary = notifier.call_args[0][0]
        assert "alpha" in summary
        assert "beta" in summary

        # 3) Dispatch on_message
        ctx = create_hook_context("on_message", text="world")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["alpha:world", "B:world"]

        # 4) Unload beta, verify alpha still works
        await manager.unload("beta")
        assert "beta" not in manager.plugins
        assert "alpha" in manager.plugins

        ctx2 = create_hook_context("on_message", text="solo")
        result2 = await manager.dispatch("on_message", ctx2)
        assert result2.results == ["alpha:solo"]

        # 5) Unload alpha
        await manager.unload("alpha")
        assert len(manager.plugins) == 0

        ctx3 = create_hook_context("on_message", text="empty")
        result3 = await manager.dispatch("on_message", ctx3)
        assert result3.results == []

    async def test_three_plugin_chain_with_gate(
        self, manager, write_yaml, plugins_dir
    ):
        """alpha(HIGH) → gamma(CRITICAL) → beta(LOW) 체인에서 gamma가 차단."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        _register_plugin("integration_plugins.beta", BetaPlugin)
        _register_plugin("integration_plugins.gamma", GammaPlugin)

        await manager.load(
            "integration_plugins.gamma",
            config={"block_keyword": "BLOCK"},
            priority=HookPriority.CRITICAL,
        )
        await manager.load(
            "integration_plugins.alpha",
            config={},
            priority=HookPriority.HIGH,
        )
        await manager.load(
            "integration_plugins.beta",
            config={"prefix": "B"},
            priority=HookPriority.LOW,
        )

        # Blocked message
        ctx_blocked = create_hook_context("on_message", text="BLOCK this")
        result_blocked = await manager.dispatch("on_message", ctx_blocked)
        assert result_blocked.stopped
        assert result_blocked.results == ["gate_closed"]

        # Clean message — gamma SKIPs, alpha and beta CONTINUE
        ctx_clean = create_hook_context("on_message", text="clean")
        result_clean = await manager.dispatch("on_message", ctx_clean)
        assert not result_clean.stopped
        assert result_clean.results == ["alpha:clean", "B:clean"]

    async def test_load_unload_reload_cycle(self, manager, notifier):
        """로드 → 언로드 → 재로드 전체 사이클."""
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        # Load
        plugin = await manager.load(
            "integration_plugins.alpha",
            config={"key": "val"},
            priority=HookPriority.HIGH,
        )
        assert plugin.meta.name == "alpha"

        # Dispatch
        ctx = create_hook_context("on_message", text="1")
        r1 = await manager.dispatch("on_message", ctx)
        assert r1.results == ["alpha:1"]

        # Reload
        _register_plugin("integration_plugins.alpha", AlphaPlugin)
        notifier.reset_mock()
        reloaded = await manager.reload("alpha")
        assert reloaded.loaded_config == {"key": "val"}

        # Dispatch after reload
        ctx2 = create_hook_context("on_message", text="2")
        r2 = await manager.dispatch("on_message", ctx2)
        assert r2.results == ["alpha:2"]

        # Unload
        await manager.unload("alpha")
        assert len(manager.plugins) == 0

        # Dispatch after unload — no handlers
        ctx3 = create_hook_context("on_message", text="3")
        r3 = await manager.dispatch("on_message", ctx3)
        assert r3.results == []


class TestNotifierIntegration:
    """알림 흐름 end-to-end 검증."""

    async def test_full_notification_sequence(self, notifier):
        """load → startup_summary → unload 알림 순서."""
        manager = PluginManager(notifier=notifier)
        _register_plugin("integration_plugins.alpha", AlphaPlugin)

        await manager.load(
            "integration_plugins.alpha", config={}, priority=HookPriority.NORMAL
        )
        load_msg = notifier.call_args[0][0]
        assert "loaded" in load_msg.lower()

        notifier.reset_mock()
        await manager.notify_startup_summary()
        summary_msg = notifier.call_args[0][0]
        assert "alpha" in summary_msg

        notifier.reset_mock()
        await manager.unload("alpha")
        unload_msg = notifier.call_args[0][0]
        assert "unloaded" in unload_msg.lower()

    async def test_notifier_failure_does_not_break_lifecycle(self):
        """알림 실패가 플러그인 생명주기를 중단하지 않음."""
        broken_notifier = AsyncMock(side_effect=RuntimeError("slack down"))
        manager = PluginManager(notifier=broken_notifier)
        _register_plugin("integration_plugins.alpha_notify", AlphaPlugin)

        # Load should succeed even though notifier fails
        plugin = await manager.load(
            "integration_plugins.alpha_notify", config={}, priority=HookPriority.NORMAL
        )
        assert plugin.meta.name == "alpha"

        # Dispatch should work
        ctx = create_hook_context("on_message", text="test")
        result = await manager.dispatch("on_message", ctx)
        assert result.results == ["alpha:test"]

        # Unload should succeed
        await manager.unload("alpha")
        assert len(manager.plugins) == 0
