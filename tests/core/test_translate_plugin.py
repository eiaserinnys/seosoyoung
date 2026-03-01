"""Tests for the translate plugin (plugins/translate/).

Tests the TranslatePlugin lifecycle, hook registration, and
message dispatch without importing Config or .env.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from seosoyoung.core.hooks import HookContext, HookResult
from seosoyoung.core.plugin import PluginMeta
from seosoyoung.core.plugin_manager import PluginManager
from seosoyoung.slackbot.plugins.translate.plugin import TranslatePlugin
from seosoyoung.slackbot.plugins.translate.detector import Language


SAMPLE_CONFIG = {
    "api_key": "test-anthropic-key",
    "openai_api_key": "test-openai-key",
    "glossary_path": "/tmp/glossary.yaml",
    "channels": ["C_TRANSLATE"],
    "backend": "openai",
    "model": "claude-sonnet-4-20250514",
    "openai_model": "gpt-5-mini",
    "context_count": 5,
    "show_glossary": False,
    "show_cost": True,
    "debug_channel": "C_DEBUG",
}


class TestTranslatePluginMeta:
    """Plugin identity."""

    def test_meta_is_plugin_meta(self):
        assert isinstance(TranslatePlugin.meta, PluginMeta)

    def test_meta_name(self):
        assert TranslatePlugin.meta.name == "translate"

    def test_meta_version(self):
        assert TranslatePlugin.meta.version == "1.0.0"


class TestTranslatePluginLifecycle:
    """on_load / on_unload."""

    @pytest.fixture()
    def plugin(self):
        return TranslatePlugin()

    @pytest.mark.asyncio
    async def test_on_load_sets_fields(self, plugin):
        await plugin.on_load(SAMPLE_CONFIG)
        assert plugin._channels == ["C_TRANSLATE"]
        assert plugin._backend == "openai"
        assert plugin._api_key == "test-anthropic-key"
        assert plugin._openai_api_key == "test-openai-key"
        assert plugin._context_count == 5
        assert plugin._show_glossary is False
        assert plugin._show_cost is True

    @pytest.mark.asyncio
    async def test_on_load_missing_key_raises(self, plugin):
        incomplete = {k: v for k, v in SAMPLE_CONFIG.items() if k != "api_key"}
        with pytest.raises(KeyError, match="api_key"):
            await plugin.on_load(incomplete)

    @pytest.mark.asyncio
    async def test_on_unload_succeeds(self, plugin):
        await plugin.on_load(SAMPLE_CONFIG)
        await plugin.on_unload()  # should not raise


class TestTranslatePluginHooks:
    """Hook registration and dispatch."""

    @pytest.fixture()
    async def loaded_plugin(self):
        p = TranslatePlugin()
        await p.on_load(SAMPLE_CONFIG)
        return p

    @pytest.mark.asyncio
    async def test_register_hooks_returns_on_message(self, loaded_plugin):
        hooks = loaded_plugin.register_hooks()
        assert "on_message" in hooks
        assert callable(hooks["on_message"])

    @pytest.mark.asyncio
    async def test_on_message_skip_for_other_channel(self, loaded_plugin):
        ctx = HookContext(
            hook_name="on_message",
            args={
                "event": {"channel": "C_OTHER", "text": "hello"},
                "client": MagicMock(),
            },
        )
        hooks = loaded_plugin.register_hooks()
        result, value = await hooks["on_message"](ctx)
        assert result == HookResult.SKIP

    @pytest.mark.asyncio
    async def test_on_message_stop_for_translate_channel(self, loaded_plugin):
        """Matching channel triggers translation (mocked) and returns STOP."""
        event = {
            "channel": "C_TRANSLATE",
            "text": "Hello world",
            "user": "U123",
            "ts": "1234.5678",
        }
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "user": {"profile": {"display_name": "Test User"}, "name": "testuser"}
        }
        mock_client.conversations_history.return_value = {"messages": []}

        ctx = HookContext(
            hook_name="on_message",
            args={"event": event, "client": mock_client},
        )

        hooks = loaded_plugin.register_hooks()
        with patch(
            "seosoyoung.slackbot.plugins.translate.plugin.translate"
        ) as mock_translate:
            mock_translate.return_value = ("안녕 세계", 0.001, [], None)
            result, value = await hooks["on_message"](ctx)

        assert result == HookResult.STOP
        assert value is True

    @pytest.mark.asyncio
    async def test_on_message_skip_bot_message(self, loaded_plugin):
        """Bot messages in translate channel should not be translated."""
        event = {
            "channel": "C_TRANSLATE",
            "text": "bot reply",
            "bot_id": "B123",
            "ts": "1234.5678",
        }
        ctx = HookContext(
            hook_name="on_message",
            args={"event": event, "client": MagicMock()},
        )
        hooks = loaded_plugin.register_hooks()
        result, value = await hooks["on_message"](ctx)
        # _process_translate returns False for bot messages -> SKIP
        assert result == HookResult.SKIP


class TestTranslatePluginManagerIntegration:
    """Integration test: load TranslatePlugin via PluginManager."""

    @pytest.mark.asyncio
    async def test_load_and_dispatch(self):
        pm = PluginManager()
        plugin = await pm.load(
            module="seosoyoung.slackbot.plugins.translate.plugin",
            config=SAMPLE_CONFIG,
            priority=50,
        )
        assert plugin.meta.name == "translate"
        assert "translate" in pm.plugins

        # Dispatch to non-matching channel -> no STOP
        ctx = HookContext(
            hook_name="on_message",
            args={
                "event": {"channel": "C_OTHER", "text": "hi"},
                "client": MagicMock(),
            },
        )
        ctx = await pm.dispatch("on_message", ctx)
        assert not ctx.stopped

    @pytest.mark.asyncio
    async def test_unload(self):
        pm = PluginManager()
        await pm.load(
            module="seosoyoung.slackbot.plugins.translate.plugin",
            config=SAMPLE_CONFIG,
        )
        await pm.unload("translate")
        assert "translate" not in pm.plugins
