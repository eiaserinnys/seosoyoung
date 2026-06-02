"""Slack thread persistent session event listener 테스트."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from seosoyoung.slackbot.presentation.session_listener import (
    DEFAULT_INACTIVITY_TIMEOUT_SECONDS,
    PersistentSessionListenerManager,
)


class FakeThread:
    created = []

    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        FakeThread.created.append(self)

    def start(self):
        self.started = True


def test_default_timeout_is_30_minutes():
    assert DEFAULT_INACTIVITY_TIMEOUT_SECONDS == 30 * 60


def test_start_or_refresh_reuses_existing_listener():
    FakeThread.created = []
    manager = PersistentSessionListenerManager(
        client_factory=MagicMock(),
        thread_factory=FakeThread,
    )
    slack_client = MagicMock()

    first = manager.start_or_refresh(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )
    second = manager.start_or_refresh(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )

    assert first is second
    assert len(FakeThread.created) == 1
    assert FakeThread.created[0].started is True


def test_record_slack_input_resets_activity_timer():
    now = [100.0]
    manager = PersistentSessionListenerManager(
        client_factory=MagicMock(),
        thread_factory=FakeThread,
        time_func=lambda: now[0],
    )
    state = manager.start_or_refresh(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=MagicMock(),
    )

    now[0] = 250.0
    manager.record_slack_input("sess-1")

    assert state.last_input_at == 250.0


@pytest.mark.asyncio
async def test_history_sync_updates_cursor():
    manager = PersistentSessionListenerManager(client_factory=MagicMock())
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=MagicMock(),
    )

    await manager._handle_history_sync(state, {"last_event_id": 42})

    assert state.last_event_id == 42


@pytest.mark.asyncio
async def test_external_user_event_posts_marker_and_resets_activity():
    now = [100.0]
    manager = PersistentSessionListenerManager(
        client_factory=MagicMock(),
        time_func=lambda: now[0],
    )
    slack_client = MagicMock()
    slack_client.chat_postMessage.return_value = {"ts": "1000.0002"}
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )
    now[0] = 150.0

    await manager._handle_external_input(
        state,
        {
            "text": "웹 입력",
            "caller_info": {"source": "browser", "display_name": "Jubok Kim"},
        },
    )

    assert state.last_input_at == 150.0
    assert state.current_callbacks is not None
    slack_client.chat_postMessage.assert_called_once_with(
        channel="C123",
        thread_ts="1000.0001",
        text="[웹] Jubok Kim: 웹 입력",
    )


@pytest.mark.asyncio
async def test_external_user_event_survives_marker_post_failure():
    manager = PersistentSessionListenerManager(client_factory=MagicMock())
    slack_client = MagicMock()
    slack_client.chat_postMessage.side_effect = Exception("Slack API error")
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )

    await manager._handle_external_input(
        state,
        {
            "text": "웹 입력",
            "caller_info": {"source": "browser", "display_name": "Jubok Kim"},
        },
    )

    assert state.current_callbacks is not None


@pytest.mark.asyncio
async def test_slack_origin_event_does_not_echo_but_resets_activity():
    now = [100.0]
    manager = PersistentSessionListenerManager(
        client_factory=MagicMock(),
        time_func=lambda: now[0],
    )
    slack_client = MagicMock()
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )
    now[0] = 180.0

    await manager._handle_external_input(
        state,
        {
            "text": "슬랙 입력",
            "caller_info": {
                "source": "slack",
                "slack": {"channel_id": "C123", "thread_ts": "1000.0001"},
            },
        },
    )

    assert state.last_input_at == 180.0
    assert state.current_callbacks is None
    slack_client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_listen_once_passes_dynamic_timeout_and_callbacks():
    client = MagicMock()
    client.listen_session_events = AsyncMock()
    manager = PersistentSessionListenerManager(
        client_factory=lambda: client,
        time_func=lambda: 100.0,
    )
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=MagicMock(),
    )
    state.last_event_id = 42

    await manager._listen_once(state)

    call = client.listen_session_events.call_args
    assert call.args == ("sess-1",)
    assert call.kwargs["last_event_id"] == 42
    assert call.kwargs["read_timeout"]() == DEFAULT_INACTIVITY_TIMEOUT_SECONDS
    assert callable(call.kwargs["on_history_sync"])
    assert callable(call.kwargs["on_user_message"])
    assert callable(call.kwargs["on_intervention_sent"])
    assert callable(call.kwargs["on_thinking"])

    close_result = client.close()
    if asyncio.iscoroutine(close_result):
        await close_result
