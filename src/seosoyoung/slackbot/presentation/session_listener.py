"""Slack thread용 background session event listener."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from seosoyoung.slackbot.presentation.activity_board import ActivityBoard, BOARD_EMPTY_TEXT
from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
from seosoyoung.slackbot.presentation.progress import (
    build_event_callbacks,
    post_initial_placeholder,
)
from seosoyoung.slackbot.presentation.session_events import (
    is_slack_origin_event,
    post_external_user_message,
)
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.soulstream.service_client import (
    ConnectionLostError,
    SessionNotFoundError,
    SoulServiceError,
)

logger = logging.getLogger(__name__)

DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 30 * 60
DEFAULT_RECONNECT_DELAY_SECONDS = 1.0


@dataclass
class _ListenerState:
    session_id: str
    channel: str
    thread_ts: str
    slack_client: Any
    timeout_seconds: float
    time_func: Callable[[], float]
    stop_event: threading.Event = field(default_factory=threading.Event)
    last_input_at: float = field(init=False)
    last_event_id: int | None = None
    current_callbacks: dict[str, Callable] | None = None

    def __post_init__(self) -> None:
        self.last_input_at = self.time_func()

    def note_input_activity(self) -> None:
        self.last_input_at = self.time_func()

    def remaining_timeout(self) -> float:
        return self.timeout_seconds - (self.time_func() - self.last_input_at)


class PersistentSessionListenerManager:
    """session_id별 background listener를 생성하고 갱신한다."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any],
        inactivity_timeout_seconds: float = DEFAULT_INACTIVITY_TIMEOUT_SECONDS,
        reconnect_delay_seconds: float = DEFAULT_RECONNECT_DELAY_SECONDS,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
        time_func: Callable[[], float] = time.monotonic,
    ):
        self._client_factory = client_factory
        self._timeout_seconds = inactivity_timeout_seconds
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._thread_factory = thread_factory
        self._time_func = time_func
        self._states: dict[str, _ListenerState] = {}
        self._lock = threading.Lock()

    def _create_state(
        self,
        session_id: str,
        *,
        channel: str,
        thread_ts: str,
        slack_client,
    ) -> _ListenerState:
        return _ListenerState(
            session_id=session_id,
            channel=channel,
            thread_ts=thread_ts,
            slack_client=slack_client,
            timeout_seconds=self._timeout_seconds,
            time_func=self._time_func,
        )

    def start_or_refresh(
        self,
        session_id: str,
        *,
        channel: str,
        thread_ts: str,
        slack_client,
    ) -> _ListenerState:
        with self._lock:
            existing = self._states.get(session_id)
            if existing:
                existing.channel = channel
                existing.thread_ts = thread_ts
                existing.slack_client = slack_client
                existing.note_input_activity()
                return existing

            state = self._create_state(
                session_id,
                channel=channel,
                thread_ts=thread_ts,
                slack_client=slack_client,
            )
            self._states[session_id] = state

        thread = self._thread_factory(
            target=lambda: self._run_state(state),
            name=f"slack-session-listener-{session_id}",
            daemon=True,
        )
        thread.start()
        logger.info(
            "[SSE:listener] started: session=%s thread_ts=%s",
            session_id,
            thread_ts,
        )
        return state

    def record_slack_input(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            state = self._states.get(session_id)
        if state:
            state.note_input_activity()

    def stop_all(self) -> None:
        with self._lock:
            states = list(self._states.values())
            self._states.clear()
        for state in states:
            state.stop_event.set()

    def _run_state(self, state: _ListenerState) -> None:
        try:
            asyncio.run(self._listen_loop(state))
        finally:
            with self._lock:
                if self._states.get(state.session_id) is state:
                    self._states.pop(state.session_id, None)

    async def _listen_loop(self, state: _ListenerState) -> None:
        while not state.stop_event.is_set():
            if state.remaining_timeout() <= 0:
                logger.info(
                    "[SSE:listener] inactivity timeout: session=%s",
                    state.session_id,
                )
                return
            try:
                await self._listen_once(state)
            except asyncio.TimeoutError:
                return
            except SessionNotFoundError:
                logger.info("[SSE:listener] session not found: %s", state.session_id)
                return
            except (ConnectionLostError, SoulServiceError) as exc:
                logger.warning(
                    "[SSE:listener] reconnect after error: session=%s err=%s",
                    state.session_id,
                    exc,
                )
            if state.remaining_timeout() <= 0:
                return
            await asyncio.sleep(self._reconnect_delay_seconds)

    async def _listen_once(self, state: _ListenerState):
        client = self._client_factory()
        try:
            return await client.listen_session_events(
                state.session_id,
                last_event_id=state.last_event_id,
                read_timeout=state.remaining_timeout,
                on_event_id=lambda event_id: self._handle_event_id(state, event_id),
                on_history_sync=lambda data: self._handle_history_sync(state, data),
                on_user_message=lambda data: self._handle_external_input(state, data),
                on_intervention_sent=lambda data: self._handle_external_input(state, data),
                on_complete=lambda data: self._handle_complete(state, data),
                on_thinking=lambda text, eid: self._dispatch_current(state, "on_thinking", text, eid),
                on_text_start=lambda eid: self._dispatch_current(state, "on_text_start", eid),
                on_text_delta=lambda text, eid: self._dispatch_current(state, "on_text_delta", text, eid),
                on_text_end=lambda eid: self._dispatch_current(state, "on_text_end", eid),
                on_tool_start=lambda name, tool_input, tool_use_id, eid: self._dispatch_current(
                    state, "on_tool_start", name, tool_input, tool_use_id, eid,
                ),
                on_tool_result=lambda result, tool_use_id, is_error, eid: self._dispatch_current(
                    state, "on_tool_result", result, tool_use_id, is_error, eid,
                ),
                on_input_request=lambda request_id, questions, agent_session_id: self._dispatch_current(
                    state, "on_input_request", request_id, questions, agent_session_id,
                ),
                on_input_request_responded=lambda request_id: self._dispatch_current(
                    state, "on_input_request_responded", request_id,
                ),
                on_input_request_expired=lambda request_id: self._dispatch_current(
                    state, "on_input_request_expired", request_id,
                ),
            )
        finally:
            close = getattr(client, "close", None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result

    async def _handle_event_id(self, state: _ListenerState, event_id: int) -> None:
        state.last_event_id = event_id

    async def _handle_history_sync(
        self,
        state: _ListenerState,
        data: dict[str, Any],
    ) -> None:
        event_id = data.get("last_event_id") or data.get("lastEventId")
        if isinstance(event_id, int):
            state.last_event_id = event_id

    async def _handle_external_input(
        self,
        state: _ListenerState,
        data: dict[str, Any],
    ) -> None:
        state.note_input_activity()
        if is_slack_origin_event(data, channel=state.channel, thread_ts=state.thread_ts):
            return

        try:
            post_external_user_message(
                state.slack_client,
                channel=state.channel,
                thread_ts=state.thread_ts,
                event_data=data,
            )
        except Exception as exc:
            logger.warning("[SSE:listener] 외부 입력 marker 게시 실패: %s", exc)
        state.current_callbacks = self._build_turn_callbacks(state)

    async def _handle_complete(
        self,
        state: _ListenerState,
        _data: dict[str, Any],
    ) -> None:
        callbacks = state.current_callbacks
        state.current_callbacks = None
        if callbacks and callbacks.get("cleanup"):
            await callbacks["cleanup"]()

    def _build_turn_callbacks(self, state: _ListenerState) -> dict[str, Callable]:
        placeholder_ts = post_initial_placeholder(
            state.slack_client,
            state.channel,
            state.thread_ts,
        )
        board = None
        try:
            reply = state.slack_client.chat_postMessage(
                channel=state.channel,
                thread_ts=state.thread_ts,
                text=BOARD_EMPTY_TEXT,
            )
            board = ActivityBoard(state.slack_client, state.channel, reply["ts"])
        except Exception as exc:
            logger.warning("[SSE:listener] placeholder B 게시 실패: %s", exc)

        pctx = PresentationContext(
            channel=state.channel,
            thread_ts=state.thread_ts,
            msg_ts=state.thread_ts,
            say=None,
            client=state.slack_client,
            effective_role="admin",
            session_id=state.session_id,
            is_existing_thread=True,
            is_thread_reply=True,
        )
        return build_event_callbacks(
            pctx,
            SlackNodeMap(),
            mode="clean",
            initial_placeholder_ts=placeholder_ts,
            initial_board=board,
        )

    async def _dispatch_current(
        self,
        state: _ListenerState,
        key: str,
        *args,
    ) -> None:
        callbacks = state.current_callbacks
        if not callbacks:
            return
        callback = callbacks.get(key)
        if callback:
            await callback(*args)
