"""Channel Observer plugin.

Collects channel messages, runs digest/judge pipelines, and
manages periodic digest scheduling. All configuration comes
from channel_observer.yaml, not from Config singleton or
environment variables.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from seosoyoung.core.hooks import HookContext, HookResult
from seosoyoung.core.plugin import Plugin, PluginMeta

logger = logging.getLogger(__name__)

# 채널별 소화 파이프라인 실행 중 여부 (중복 실행 방지)
_digest_running: dict[str, bool] = {}
_digest_lock = threading.Lock()


class ChannelObserverPlugin(Plugin):
    """Channel observation and digest management plugin.

    Collects messages from monitored channels via on_message hook,
    triggers digest/judge pipelines when thresholds are met, and
    runs a periodic scheduler via on_startup hook.

    No self.enabled flag — if loaded, it's active.
    PluginMeta에 dependencies 없음 — plugins.yaml depends_on이 정본.
    """

    meta = PluginMeta(
        name="channel_observer",
        version="1.0.0",
        description="Channel message observation and digest management",
    )

    async def on_load(self, config: dict[str, Any]) -> None:
        self._config = config

        # Core settings
        self._channels: list[str] = config.get("channels", [])
        self._api_key: str = config.get("api_key", "")
        self._model: str = config.get("model", "gpt-5-mini")
        self._compressor_model: str = config.get(
            "compressor_model", "gpt-5.2"
        )
        self._memory_path: str = config["memory_path"]

        # Thresholds
        self._threshold_a: int = config.get("threshold_a", 150)
        self._threshold_b: int = config.get("threshold_b", 5000)
        self._buffer_threshold: int = config.get("buffer_threshold", 150)
        self._digest_max_tokens: int = config.get("digest_max_tokens", 10000)
        self._digest_target_tokens: int = config.get(
            "digest_target_tokens", 5000
        )
        self._intervention_threshold: float = config.get(
            "intervention_threshold", 0.18
        )
        self._periodic_sec: int = config.get("periodic_sec", 300)
        self._trigger_words: list[str] = config.get("trigger_words", [])
        self._debug_channel: str = config.get("debug_channel", "")

        # Runtime components (initialized in on_startup)
        self._store = None
        self._collector = None
        self._cooldown = None
        self._observer_engine = None
        self._compressor = None
        self._scheduler = None
        self._slack_client = None
        self._mention_tracker = None

        logger.info(
            "ChannelObserverPlugin loaded: channels=%s, threshold_a=%d",
            self._channels,
            self._threshold_a,
        )

    async def on_unload(self) -> None:
        if self._scheduler:
            self._scheduler.stop()
            logger.info("ChannelObserverPlugin: scheduler stopped")

    def register_hooks(self) -> dict:
        return {
            "on_message": self._on_message,
            "on_startup": self._on_startup,
            "on_shutdown": self._on_shutdown,
        }

    # -- Hook handlers ---------------------------------------------------------

    async def _on_startup(
        self, ctx: HookContext
    ) -> tuple[HookResult, Any]:
        """Initialize runtime components and start periodic scheduler.

        Receives runtime dependencies via ctx.args from main.py.
        """
        if not self._channels:
            logger.info("ChannelObserverPlugin: no channels configured")
            return HookResult.CONTINUE, None

        self._slack_client = ctx.args.get("slack_client")
        self._mention_tracker = ctx.args.get("mention_tracker")
        self._bot_user_id = ctx.args.get("bot_user_id", "")

        from seosoyoung.slackbot.plugins.channel_observer.store import (
            ChannelStore,
        )
        from seosoyoung.slackbot.plugins.channel_observer.collector import (
            ChannelMessageCollector,
        )
        from seosoyoung.slackbot.plugins.channel_observer.intervention import (
            InterventionHistory,
        )
        from seosoyoung.slackbot.plugins.channel_observer.observer import (
            ChannelObserver,
            DigestCompressor,
        )
        from seosoyoung.slackbot.plugins.channel_observer.scheduler import (
            ChannelDigestScheduler,
        )

        self._store = ChannelStore(base_dir=self._memory_path)
        self._collector = ChannelMessageCollector(
            store=self._store,
            target_channels=self._channels,
            mention_tracker=self._mention_tracker,
            bot_user_id=self._bot_user_id,
        )
        self._cooldown = InterventionHistory(base_dir=self._memory_path)

        if self._api_key:
            self._observer_engine = ChannelObserver(
                api_key=self._api_key,
                model=self._model,
            )
            self._compressor = DigestCompressor(
                api_key=self._api_key,
                model=self._compressor_model,
            )

        if self._observer_engine and self._periodic_sec > 0:
            self._scheduler = ChannelDigestScheduler(
                store=self._store,
                observer=self._observer_engine,
                compressor=self._compressor,
                cooldown=self._cooldown,
                slack_client=self._slack_client,
                channels=self._channels,
                interval_sec=self._periodic_sec,
                buffer_threshold=self._buffer_threshold,
                digest_max_tokens=self._digest_max_tokens,
                digest_target_tokens=self._digest_target_tokens,
                debug_channel=self._debug_channel,
                intervention_threshold=self._intervention_threshold,
                mention_tracker=self._mention_tracker,
                bot_user_id=self._bot_user_id,
            )
            self._scheduler.start()

        logger.info(
            "ChannelObserverPlugin started: channels=%s, "
            "threshold=%s, periodic=%ds",
            self._channels,
            self._intervention_threshold,
            self._periodic_sec,
        )

        # Return references for handler access
        return HookResult.CONTINUE, {
            "channel_store": self._store,
            "channel_collector": self._collector,
            "channel_cooldown": self._cooldown,
            "channel_observer": self._observer_engine,
            "channel_compressor": self._compressor,
            "channel_observer_channels": self._channels,
        }

    async def _on_shutdown(
        self, ctx: HookContext
    ) -> tuple[HookResult, Any]:
        """Stop scheduler on shutdown."""
        if self._scheduler:
            self._scheduler.stop()
        return HookResult.CONTINUE, None

    async def _on_message(
        self, ctx: HookContext
    ) -> tuple[HookResult, Any]:
        """Collect channel messages and trigger digest pipeline.

        This runs before other on_message hooks (priority=20 in
        plugins.yaml, but runs first because higher priority goes first).
        """
        if not self._collector:
            return HookResult.SKIP, None

        event = ctx.args.get("event", {})
        client = ctx.args.get("client")

        channel = event.get("channel", "")
        if channel not in self._channels:
            return HookResult.SKIP, None

        try:
            collected = self._collector.collect(event)
            if collected:
                self._send_collect_log(client, channel, event)
                force = self._contains_trigger_word(
                    event.get("text", "")
                )
                self._maybe_trigger_digest(channel, client, force=force)
        except Exception as e:
            logger.error(f"채널 메시지 수집 실패: {e}")

        # Also handle reactions collection for message events
        # (actual reaction events are handled separately)

        # SKIP — don't stop the chain, let other plugins process
        return HookResult.SKIP, None

    # -- Reaction collection (called from message handler) ---------------------

    def collect_reaction(self, event: dict, action: str) -> bool:
        """Collect reaction events for channel observation.

        Called directly from message handler, not via hook dispatch.
        """
        if not self._collector:
            return False
        return self._collector.collect_reaction(event, action)

    # -- Accessors for runtime references --------------------------------------

    @property
    def store(self) -> Any:
        """ChannelStore instance (for session_context hybrid mode)."""
        return self._store

    @property
    def channels(self) -> list[str]:
        """Monitored channel IDs."""
        return self._channels

    # -- Internal helpers ------------------------------------------------------

    def _contains_trigger_word(self, text: str) -> bool:
        """텍스트에 트리거 워드가 포함되어 있는지 확인합니다."""
        if not self._trigger_words:
            return False
        text_lower = text.lower()
        return any(
            word.lower() in text_lower for word in self._trigger_words
        )

    def _maybe_trigger_digest(
        self, channel_id: str, client: Any, *, force: bool = False
    ) -> None:
        """pending 토큰이 threshold_A 이상이면 파이프라인을 실행합니다."""
        if not all([self._store, self._observer_engine, self._cooldown]):
            return

        pending_tokens = self._store.count_pending_tokens(channel_id)
        if not force and pending_tokens < self._threshold_a:
            return

        with _digest_lock:
            if _digest_running.get(channel_id):
                return
            _digest_running[channel_id] = True

        threshold_a = 1 if force else self._threshold_a

        def run():
            try:
                from seosoyoung.slackbot.plugins.channel_observer.pipeline import (
                    run_channel_pipeline,
                )
                from seosoyoung.slackbot.claude import get_claude_runner
                from seosoyoung.utils.async_bridge import run_in_new_loop

                runner = get_claude_runner()

                run_in_new_loop(
                    run_channel_pipeline(
                        store=self._store,
                        observer=self._observer_engine,
                        channel_id=channel_id,
                        slack_client=client,
                        cooldown=self._cooldown,
                        threshold_a=threshold_a,
                        threshold_b=self._threshold_b,
                        compressor=self._compressor,
                        digest_max_tokens=self._digest_max_tokens,
                        digest_target_tokens=self._digest_target_tokens,
                        debug_channel=self._debug_channel,
                        intervention_threshold=self._intervention_threshold,
                        claude_runner=runner,
                        bot_user_id=self._bot_user_id,
                        mention_tracker=self._mention_tracker,
                    )
                )
            except Exception as e:
                logger.error(
                    f"채널 파이프라인 실행 실패 ({channel_id}): {e}"
                )
            finally:
                with _digest_lock:
                    _digest_running[channel_id] = False

        digest_thread = threading.Thread(target=run, daemon=True)
        digest_thread.start()

    def _send_collect_log(
        self, client: Any, channel_id: str, event: dict
    ) -> None:
        """수집 디버그 로그를 전송합니다."""
        if not self._debug_channel:
            return
        try:
            from seosoyoung.slackbot.plugins.channel_observer.intervention import (
                send_collect_debug_log,
            )

            if event.get("subtype") == "message_changed":
                source = event.get("message", {})
            else:
                source = event

            buffer_tokens = (
                self._store.count_pending_tokens(channel_id)
                if self._store
                else 0
            )
            send_collect_debug_log(
                client=client,
                debug_channel=self._debug_channel,
                source_channel=channel_id,
                buffer_tokens=buffer_tokens,
                threshold=self._threshold_a,
                message_text=source.get("text", ""),
                user=source.get("user", ""),
                is_thread=bool(
                    source.get("thread_ts") or event.get("thread_ts")
                ),
            )
        except Exception as e:
            logger.error(f"수집 디버그 로그 전송 실패: {e}")
