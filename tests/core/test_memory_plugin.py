"""Tests for the memory plugin (plugins/memory/).

Tests the MemoryPlugin lifecycle, hook registration, and
before_execute / after_execute dispatch without importing Config or .env.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from seosoyoung.core.hooks import HookContext, HookResult
from seosoyoung.core.plugin import PluginMeta
from seosoyoung.core.plugin_manager import PluginManager
from seosoyoung.slackbot.plugins.memory.plugin import MemoryPlugin


SAMPLE_CONFIG = {
    "openai_api_key": "test-openai-key",
    "model": "gpt-5-mini",
    "memory_path": "/tmp/test_memory",
    "debug_channel": "C_DEBUG",
    "max_observation_tokens": 30000,
    "min_turn_tokens": 200,
    "reflection_threshold": 20000,
    "promoter_model": "gpt-5.2",
    "promotion_threshold": 5000,
    "persistent_compaction_threshold": 15000,
    "persistent_compaction_target": 8000,
    "emoji": {
        "text_session_start": ":ssy-surprise:",
        "text_ltm_inject": ":ssy-thinking:",
    },
}


class TestMemoryPluginMeta:
    """Plugin identity."""

    def test_meta_is_plugin_meta(self):
        assert isinstance(MemoryPlugin.meta, PluginMeta)

    def test_meta_name(self):
        assert MemoryPlugin.meta.name == "memory"

    def test_meta_version(self):
        assert MemoryPlugin.meta.version == "1.0.0"


class TestMemoryPluginLifecycle:
    """on_load / on_unload."""

    @pytest.fixture()
    def plugin(self):
        return MemoryPlugin()

    @pytest.mark.asyncio
    async def test_on_load_sets_fields(self, plugin):
        await plugin.on_load(SAMPLE_CONFIG)
        assert plugin._openai_api_key == "test-openai-key"
        assert plugin._model == "gpt-5-mini"
        assert plugin._memory_path == "/tmp/test_memory"
        assert plugin._debug_channel == "C_DEBUG"
        assert plugin._max_observation_tokens == 30000
        assert plugin._min_turn_tokens == 200
        assert plugin._promoter_model == "gpt-5.2"
        assert plugin._emoji["text_session_start"] == ":ssy-surprise:"

    @pytest.mark.asyncio
    async def test_on_load_missing_required_key_raises(self, plugin):
        incomplete = {
            k: v for k, v in SAMPLE_CONFIG.items() if k != "openai_api_key"
        }
        with pytest.raises(KeyError, match="openai_api_key"):
            await plugin.on_load(incomplete)

    @pytest.mark.asyncio
    async def test_on_load_missing_memory_path_raises(self, plugin):
        incomplete = {
            k: v for k, v in SAMPLE_CONFIG.items() if k != "memory_path"
        }
        with pytest.raises(KeyError, match="memory_path"):
            await plugin.on_load(incomplete)

    @pytest.mark.asyncio
    async def test_on_unload_succeeds(self, plugin):
        await plugin.on_load(SAMPLE_CONFIG)
        await plugin.on_unload()  # should not raise


class TestMemoryPluginHooks:
    """Hook registration and dispatch."""

    @pytest.fixture()
    async def loaded_plugin(self):
        p = MemoryPlugin()
        await p.on_load(SAMPLE_CONFIG)
        return p

    @pytest.mark.asyncio
    async def test_register_hooks_returns_before_and_after_execute(
        self, loaded_plugin
    ):
        hooks = loaded_plugin.register_hooks()
        assert "before_execute" in hooks
        assert "after_execute" in hooks
        assert callable(hooks["before_execute"])
        assert callable(hooks["after_execute"])

    @pytest.mark.asyncio
    async def test_before_execute_skip_when_no_thread_ts(self, loaded_plugin):
        ctx = HookContext(
            hook_name="before_execute",
            args={"prompt": "hello", "channel": "C123"},
        )
        hooks = loaded_plugin.register_hooks()
        result, value = await hooks["before_execute"](ctx)
        assert result == HookResult.CONTINUE
        assert value is None

    @pytest.mark.asyncio
    async def test_before_execute_injects_memory(self, loaded_plugin):
        """before_execute should inject memory prompt when injection succeeds."""
        mock_result = MagicMock()
        mock_result.prompt = "memory context here"
        mock_result.persistent_tokens = 100
        mock_result.session_tokens = 0
        mock_result.channel_digest_tokens = 0
        mock_result.channel_buffer_tokens = 0
        mock_result.new_observation_tokens = 0
        mock_result.persistent_content = "ltm content"

        with patch.object(
            loaded_plugin,
            "_prepare_injection",
            return_value=("memory context here", "anchor123"),
        ):
            ctx = HookContext(
                hook_name="before_execute",
                args={
                    "thread_ts": "1234.5678",
                    "channel": "C123",
                    "session_id": None,
                    "prompt": "user question",
                    "channel_observer_channels": [],
                },
            )
            hooks = loaded_plugin.register_hooks()
            result, value = await hooks["before_execute"](ctx)

            assert result == HookResult.CONTINUE
            assert isinstance(value, dict)
            assert "prompt" in value
            assert "memory context here" in value["prompt"]
            assert "user question" in value["prompt"]
            assert value["anchor_ts"] == "anchor123"

    @pytest.mark.asyncio
    async def test_before_execute_no_injection(self, loaded_plugin):
        """before_execute should return anchor but no prompt when no memory."""
        with patch.object(
            loaded_plugin,
            "_prepare_injection",
            return_value=(None, "anchor456"),
        ):
            ctx = HookContext(
                hook_name="before_execute",
                args={
                    "thread_ts": "1234.5678",
                    "channel": "C123",
                    "session_id": "sess1",
                    "prompt": "hello",
                    "channel_observer_channels": [],
                },
            )
            hooks = loaded_plugin.register_hooks()
            result, value = await hooks["before_execute"](ctx)

            assert result == HookResult.CONTINUE
            assert isinstance(value, dict)
            assert "prompt" not in value
            assert value["anchor_ts"] == "anchor456"

    @pytest.mark.asyncio
    async def test_before_execute_error_graceful(self, loaded_plugin):
        """before_execute should catch exceptions and continue."""
        with patch.object(
            loaded_plugin,
            "_prepare_injection",
            side_effect=RuntimeError("DB error"),
        ):
            ctx = HookContext(
                hook_name="before_execute",
                args={
                    "thread_ts": "1234.5678",
                    "channel": "C123",
                    "session_id": None,
                    "prompt": "hello",
                },
            )
            hooks = loaded_plugin.register_hooks()
            result, value = await hooks["before_execute"](ctx)

            assert result == HookResult.CONTINUE
            assert value is None

    @pytest.mark.asyncio
    async def test_after_execute_skip_when_missing_args(self, loaded_plugin):
        ctx = HookContext(
            hook_name="after_execute",
            args={"thread_ts": "", "user_id": ""},
        )
        hooks = loaded_plugin.register_hooks()
        result, value = await hooks["after_execute"](ctx)
        assert result == HookResult.CONTINUE
        assert value is None

    @pytest.mark.asyncio
    async def test_after_execute_triggers_observation(self, loaded_plugin):
        """after_execute should call _trigger_observation."""
        with patch.object(
            loaded_plugin, "_trigger_observation"
        ) as mock_trigger:
            ctx = HookContext(
                hook_name="after_execute",
                args={
                    "thread_ts": "1234.5678",
                    "user_id": "U123",
                    "prompt": "user message",
                    "collected_messages": [
                        {"role": "assistant", "content": "response"},
                    ],
                    "anchor_ts": "anchor789",
                },
            )
            hooks = loaded_plugin.register_hooks()
            result, value = await hooks["after_execute"](ctx)

            assert result == HookResult.CONTINUE
            mock_trigger.assert_called_once_with(
                "1234.5678",
                "U123",
                "user message",
                [{"role": "assistant", "content": "response"}],
                "anchor789",
            )


class TestMemoryPluginCompactFlag:
    """on_compact_flag method."""

    @pytest.fixture()
    async def loaded_plugin(self):
        p = MemoryPlugin()
        await p.on_load(SAMPLE_CONFIG)
        return p

    @pytest.mark.asyncio
    async def test_on_compact_flag_sets_inject_flag(self, loaded_plugin):
        mock_record = MagicMock()
        mock_record.observations = "some observations"

        mock_store = MagicMock()
        mock_store.get_record.return_value = mock_record

        with patch(
            "seosoyoung.slackbot.plugins.memory.store.MemoryStore",
            return_value=mock_store,
        ):
            loaded_plugin.on_compact_flag("thread123")
            mock_store.set_inject_flag.assert_called_once_with("thread123")

    @pytest.mark.asyncio
    async def test_on_compact_flag_no_record(self, loaded_plugin):
        mock_store = MagicMock()
        mock_store.get_record.return_value = None

        with patch(
            "seosoyoung.slackbot.plugins.memory.store.MemoryStore",
            return_value=mock_store,
        ):
            loaded_plugin.on_compact_flag("thread123")
            mock_store.set_inject_flag.assert_not_called()


class TestMemoryPluginManagerIntegration:
    """End-to-end with PluginManager."""

    @pytest.mark.asyncio
    async def test_load_and_dispatch_before_execute(self):
        pm = PluginManager(notifier=AsyncMock())

        with patch.object(
            MemoryPlugin,
            "_prepare_injection",
            return_value=("injected memory", "anchor_ts_1"),
        ):
            await pm.load(
                module="seosoyoung.slackbot.plugins.memory.plugin",
                config=SAMPLE_CONFIG,
                priority=50,
            )

            ctx = HookContext(
                hook_name="before_execute",
                args={
                    "thread_ts": "9999.1234",
                    "channel": "C_TEST",
                    "session_id": None,
                    "prompt": "test prompt",
                    "channel_observer_channels": [],
                },
            )
            ctx = await pm.dispatch("before_execute", ctx)

            assert len(ctx.results) == 1
            result_dict = ctx.results[0]
            assert isinstance(result_dict, dict)
            assert "prompt" in result_dict
            assert "injected memory" in result_dict["prompt"]
