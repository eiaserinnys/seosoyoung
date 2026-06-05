"""Slack thread persistent session event listener 테스트."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from seosoyoung.slackbot.presentation.activity_board import BOARD_EMPTY_TEXT
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
    assert slack_client.chat_postMessage.call_count == 3
    slack_client.chat_postMessage.assert_any_call(
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
@patch("seosoyoung.slackbot.presentation.progress._event_delete_delay", return_value=3600)
@patch("seosoyoung.slackbot.presentation.progress._thinking_delete_delay", return_value=3600)
async def test_external_turn_uses_activity_board_clean_mode(_thinking_delay, _event_delay):
    manager = PersistentSessionListenerManager(client_factory=MagicMock())
    slack_client = MagicMock()
    slack_client.chat_postMessage.side_effect = [
        {"ts": "marker-ts"},
        {"ts": "placeholder-a-ts"},
        {"ts": "board-ts"},
    ]
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
    await manager._dispatch_current(state, "on_thinking", "검토 중", 101)
    await manager._dispatch_current(
        state, "on_tool_start", "Read", {"file_path": "/tmp/a.txt"}, "toolu-1", 102,
    )
    await manager._dispatch_current(
        state, "on_tool_result", "file contents", "toolu-1", False, 103,
    )

    assert slack_client.chat_postMessage.call_count == 3
    board_post = slack_client.chat_postMessage.call_args_list[2].kwargs
    assert board_post == {
        "channel": "C123",
        "thread_ts": "1000.0001",
        "text": BOARD_EMPTY_TEXT,
    }
    assert slack_client.chat_update.call_count == 3
    assert all(c.kwargs["ts"] == "board-ts" for c in slack_client.chat_update.call_args_list)
    rendered_updates = "\n".join(c.kwargs["text"] for c in slack_client.chat_update.call_args_list)
    assert "검토 중" in rendered_updates
    assert "Read" in rendered_updates
    assert "file contents" in rendered_updates

    await manager._handle_complete(state, {})

    slack_client.chat_delete.assert_has_calls([
        call(channel="C123", ts="placeholder-a-ts"),
        call(channel="C123", ts="board-ts"),
    ])


def test_build_turn_callbacks_passes_clean_mode_placeholders():
    manager = PersistentSessionListenerManager(client_factory=MagicMock())
    slack_client = MagicMock()
    slack_client.chat_postMessage.return_value = {"ts": "board-ts"}
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )
    expected_callbacks = {"cleanup": AsyncMock()}
    board = MagicMock(name="board")

    with (
        patch(
            "seosoyoung.slackbot.presentation.session_listener.post_initial_placeholder",
            return_value="placeholder-a-ts",
        ) as mock_post_placeholder,
        patch(
            "seosoyoung.slackbot.presentation.session_listener.ActivityBoard",
            return_value=board,
        ) as mock_board_cls,
        patch(
            "seosoyoung.slackbot.presentation.session_listener.build_event_callbacks",
            return_value=expected_callbacks,
        ) as mock_build_callbacks,
    ):
        callbacks = manager._build_turn_callbacks(state)

    assert callbacks is expected_callbacks
    mock_post_placeholder.assert_called_once_with(slack_client, "C123", "1000.0001")
    slack_client.chat_postMessage.assert_called_once_with(
        channel="C123",
        thread_ts="1000.0001",
        text=BOARD_EMPTY_TEXT,
    )
    mock_board_cls.assert_called_once_with(slack_client, "C123", "board-ts")
    call_args = mock_build_callbacks.call_args
    assert call_args.args[1].__class__.__name__ == "SlackNodeMap"
    assert call_args.kwargs["mode"] == "clean"
    assert call_args.kwargs["initial_placeholder_ts"] == "placeholder-a-ts"
    assert call_args.kwargs["initial_board"] is board


@pytest.mark.asyncio
@patch("seosoyoung.slackbot.presentation.progress._thinking_delete_delay", return_value=3600)
async def test_external_turn_cleanup_isolated_per_turn(_thinking_delay):
    manager = PersistentSessionListenerManager(client_factory=MagicMock())
    slack_client = MagicMock()
    slack_client.chat_postMessage.side_effect = [
        {"ts": "marker-1"},
        {"ts": "placeholder-a-1"},
        {"ts": "board-1"},
        {"ts": "marker-2"},
        {"ts": "placeholder-a-2"},
        {"ts": "board-2"},
    ]
    state = manager._create_state(
        "sess-1", channel="C123", thread_ts="1000.0001", slack_client=slack_client,
    )

    await manager._handle_external_input(
        state,
        {
            "text": "첫 번째 웹 입력",
            "caller_info": {"source": "browser", "display_name": "Jubok Kim"},
        },
    )
    await manager._dispatch_current(state, "on_thinking", "첫 번째 검토", 101)
    await manager._handle_complete(state, {})

    slack_client.chat_delete.assert_has_calls([
        call(channel="C123", ts="placeholder-a-1"),
        call(channel="C123", ts="board-1"),
    ])
    first_turn_delete_count = slack_client.chat_delete.call_count

    await manager._handle_external_input(
        state,
        {
            "text": "두 번째 웹 입력",
            "caller_info": {"source": "browser", "display_name": "Jubok Kim"},
        },
    )
    assert slack_client.chat_delete.call_count == first_turn_delete_count

    await manager._dispatch_current(state, "on_thinking", "두 번째 검토", 201)
    await manager._handle_complete(state, {})

    slack_client.chat_delete.assert_has_calls([
        call(channel="C123", ts="placeholder-a-2"),
        call(channel="C123", ts="board-2"),
    ])


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
