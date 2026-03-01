"""Trello plugin.

Trello watcher, list runner, reaction-based execution, and
resume command handling. All configuration comes from trello.yaml,
not from Config singleton or environment variables.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Any, Optional

from seosoyoung.core.hooks import HookContext, HookResult
from seosoyoung.core.plugin import Plugin, PluginMeta

from seosoyoung.slackbot.plugins.trello.client import TrelloClient
from seosoyoung.slackbot.plugins.trello.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)

_RESUME_PATTERNS = [
    re.compile(r"정주행\s*(을\s*)?재개", re.IGNORECASE),
    re.compile(r"리스트런\s*(을\s*)?재개", re.IGNORECASE),
    re.compile(r"resume\s*(list\s*)?run", re.IGNORECASE),
]


class TrelloPlugin(Plugin):
    """Trello watcher and card management plugin.

    Manages TrelloWatcher lifecycle and handles reaction-based
    execution and list-run resume commands.
    """

    meta = PluginMeta(
        name="trello",
        version="1.0.0",
        description="Trello watcher and card management",
    )

    async def on_load(self, config: dict[str, Any]) -> None:
        self._config = config

        self._trello = TrelloClient(
            api_key=config["api_key"],
            token=config["token"],
            board_id=config["board_id"],
        )

        self._prompt_builder = PromptBuilder(
            self._trello,
            list_ids=config["list_ids"],
        )

        # Runtime dependencies, injected via on_startup hook.
        self._slack_client = None
        self._session_manager = None
        self._claude_runner_factory = None
        self._get_session_lock = None
        self._restart_manager = None
        self._update_message_fn = None
        self._watcher = None
        self._list_runner = None

        logger.info(
            "TrelloPlugin loaded: board_id=%s, execute_emoji=%s",
            config["board_id"],
            config["execute_emoji"],
        )

    async def on_unload(self) -> None:
        if self._watcher:
            self._watcher.stop()
            logger.info("TrelloPlugin: watcher stopped")

    def register_hooks(self) -> dict:
        return {
            "on_startup": self._on_startup,
            "on_shutdown": self._on_shutdown,
            "on_reaction": self._on_reaction,
            "on_command": self._on_command,
        }

    # -- Hook handlers ---------------------------------------------------------

    async def _on_startup(self, ctx: HookContext) -> tuple[HookResult, Any]:
        """Receive runtime dependencies and start watcher."""
        from seosoyoung.slackbot.plugins.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.plugins.trello.list_runner import ListRunner

        self._slack_client = ctx.args["slack_client"]
        self._session_manager = ctx.args["session_manager"]
        self._claude_runner_factory = ctx.args["claude_runner_factory"]
        self._get_session_lock = ctx.args.get("get_session_lock")
        self._restart_manager = ctx.args.get("restart_manager")
        self._update_message_fn = ctx.args.get("update_message_fn")

        data_dir = ctx.args.get("data_dir")
        self._list_runner = ListRunner(data_dir=data_dir)

        self._watcher = TrelloWatcher(
            trello_client=self._trello,
            prompt_builder=self._prompt_builder,
            slack_client=self._slack_client,
            session_manager=self._session_manager,
            claude_runner_factory=self._claude_runner_factory,
            config=self._config,
            get_session_lock=self._get_session_lock,
            data_dir=data_dir,
            list_runner_ref=lambda: self._list_runner,
        )
        self._watcher.start()

        logger.info("TrelloPlugin: watcher and list_runner started")

        return HookResult.CONTINUE, {
            "watcher": self._watcher,
            "list_runner": self._list_runner,
        }

    async def _on_shutdown(self, ctx: HookContext) -> tuple[HookResult, Any]:
        """Stop watcher on shutdown."""
        if self._watcher:
            self._watcher.stop()
        return HookResult.CONTINUE, None

    async def _on_reaction(self, ctx: HookContext) -> tuple[HookResult, Any]:
        """Handle execute emoji reaction on trello watcher threads."""
        from seosoyoung.utils.async_bridge import run_in_new_loop
        from seosoyoung.slackbot.claude import get_claude_runner

        event = ctx.args["event"]
        client = ctx.args["client"]

        reaction = event.get("reaction", "")
        item = event.get("item", {})
        item_ts = item.get("ts", "")
        item_channel = item.get("channel", "")
        user_id = event.get("user", "")

        # 1. Check if this is the execute emoji
        if reaction != self._config["execute_emoji"]:
            return HookResult.SKIP, None

        logger.info(
            "Execute reaction detected: %s on %s by %s",
            reaction, item_ts, user_id,
        )

        # 2. Check watcher is available
        if not self._watcher:
            logger.debug("Watcher not available.")
            return HookResult.SKIP, None

        # 3. Look up ThreadCardInfo
        tracked = self._watcher.get_tracked_by_thread_ts(item_ts)
        if not tracked:
            logger.debug("ThreadCardInfo not found: %s", item_ts)
            return HookResult.SKIP, None

        logger.info(
            "ThreadCardInfo found: %s (card_id=%s)",
            tracked.card_name, tracked.card_id,
        )

        # 4. Get or create session
        session = self._session_manager.get(item_ts)
        if not session:
            logger.warning("Session not found: %s, creating new", item_ts)
            session = self._session_manager.create(
                thread_ts=item_ts,
                channel_id=item_channel,
                user_id=user_id,
                username="reaction_executor",
                role="admin",
            )

        # 5. Check restart pending
        if self._restart_manager and self._restart_manager.is_pending:
            try:
                client.chat_postMessage(
                    channel=item_channel,
                    thread_ts=item_ts,
                    text="재시작을 대기하는 중입니다. 재시작이 완료되면 다시 시도해주세요.",
                )
            except Exception as e:
                logger.error("Failed to send restart-pending message: %s", e)
            return HookResult.STOP, None

        # 6. Post start notification
        try:
            start_msg = client.chat_postMessage(
                channel=item_channel,
                thread_ts=item_ts,
                text="`\U0001f680 리액션으로 실행을 시작합니다. 세션을 정리하는 중...`",
            )
            start_msg_ts = start_msg["ts"]
        except Exception as e:
            logger.error("Failed to send start notification: %s", e)
            return HookResult.STOP, None

        # 7. Build execute prompt
        prompt = self._watcher.build_reaction_execute_prompt(tracked)

        # 8. Set has_execute flag
        tracked.has_execute = True

        # 9. Run compact + Claude in background thread
        session_manager = self._session_manager
        get_session_lock = self._get_session_lock
        update_message_fn = self._update_message_fn
        claude_runner_factory = self._claude_runner_factory

        def run_with_compact():
            lock = None
            if get_session_lock:
                lock = get_session_lock(item_ts)
                if not lock.acquire(blocking=False):
                    try:
                        client.chat_update(
                            channel=item_channel,
                            ts=start_msg_ts,
                            text="이전 요청을 처리 중이에요. 잠시 후 다시 시도해주세요.",
                        )
                    except Exception:
                        pass
                    return

            try:
                # Compact
                if session.session_id:
                    try:
                        client.chat_update(
                            channel=item_channel,
                            ts=start_msg_ts,
                            text="`\U0001f680 세션 정리 중... (compact)`",
                        )
                        runner = get_claude_runner()
                        compact_result = run_in_new_loop(
                            runner.compact_session(session.session_id)
                        )
                        if compact_result.success:
                            logger.info(
                                "Session compact success: %s",
                                session.session_id,
                            )
                        else:
                            logger.warning(
                                "Session compact failed: %s",
                                compact_result.error,
                            )
                        if compact_result.session_id:
                            session_manager.update_session_id(
                                item_ts, compact_result.session_id
                            )
                    except Exception as e:
                        logger.error("Session compact error: %s", e)

                # say function
                def say(text, thread_ts=None):
                    client.chat_postMessage(
                        channel=item_channel,
                        thread_ts=thread_ts or item_ts,
                        text=text,
                    )

                # PresentationContext
                from seosoyoung.slackbot.presentation.types import PresentationContext
                from seosoyoung.slackbot.presentation.progress import (
                    build_progress_callbacks,
                )

                pctx = PresentationContext(
                    channel=item_channel,
                    thread_ts=item_ts,
                    msg_ts=start_msg_ts,
                    say=say,
                    client=client,
                    effective_role="admin",
                    session_id=session.session_id,
                    user_id=user_id,
                    last_msg_ts=start_msg_ts,
                    main_msg_ts=start_msg_ts,
                    trello_card=tracked,
                    is_trello_mode=True,
                )

                on_progress, on_compact = build_progress_callbacks(
                    pctx, update_message_fn
                )

                # Run Claude
                claude_runner_factory(
                    prompt=prompt,
                    thread_ts=item_ts,
                    msg_ts=start_msg_ts,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    presentation=pctx,
                    session_id=session.session_id,
                    role="admin",
                )

            except Exception as e:
                logger.exception("Reaction-based execution error: %s", e)
                try:
                    client.chat_update(
                        channel=item_channel,
                        ts=start_msg_ts,
                        text=f"\u274c 실행 오류: {e}",
                    )
                except Exception:
                    pass
            finally:
                if lock:
                    lock.release()

        execute_thread = threading.Thread(target=run_with_compact, daemon=True)
        execute_thread.start()

        return HookResult.STOP, None

    async def _on_command(self, ctx: HookContext) -> tuple[HookResult, Any]:
        """Handle resume list-run command."""
        command = ctx.args.get("command", "")

        if not _is_resume_command(command):
            return HookResult.SKIP, None

        if not self._list_runner:
            return HookResult.SKIP, None

        say = ctx.args.get("say")
        ts = ctx.args.get("ts")
        thread_ts = ctx.args.get("thread_ts")

        paused = self._list_runner.get_paused_sessions()
        if not paused:
            if say:
                say(
                    text="현재 중단된 정주행 세션이 없습니다.",
                    thread_ts=thread_ts or ts,
                )
            return HookResult.STOP, None

        # Resume the most recent paused session
        session = paused[-1]
        if self._list_runner.resume_run(session.session_id):
            if say:
                say(
                    text=(
                        f"\u25b6\ufe0f 정주행 재개: "
                        f"`{session.session_id}` ({session.list_name})\n"
                        f"진행: {session.current_index}/{len(session.card_ids)}"
                    ),
                    thread_ts=thread_ts or ts,
                )
            # Trigger watcher to process next card
            if self._watcher:
                notify_channel = self._config["notify_channel"]
                t = threading.Thread(
                    target=self._watcher._process_list_run_card,
                    args=(session.session_id, thread_ts or ts, notify_channel),
                    daemon=True,
                )
                t.start()
        else:
            if say:
                say(
                    text="정주행 재개에 실패했습니다.",
                    thread_ts=thread_ts or ts,
                )

        return HookResult.STOP, None


def _is_resume_command(command: str) -> bool:
    """Check if the command matches a resume list-run pattern."""
    for pattern in _RESUME_PATTERNS:
        if pattern.search(command):
            return True
    return False
