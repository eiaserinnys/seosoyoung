from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import json

from seosoyoung.slackbot.daily_todo.parser import parse_daily_todo_card
from seosoyoung.slackbot.handlers.daily_todo import (
    parse_number_reply,
    register_daily_todo_handlers,
    try_handle_number_reply,
)
from seosoyoung.slackbot.daily_todo.publisher import (
    EXPECTED_BOT_USER_ID,
    EXPECTED_RECIPIENT_USER_ID,
)


def test_number_reply_parser_accepts_only_the_complete_number_list_forms():
    assert parse_number_reply("1, 3 완료") == [1, 3]
    assert parse_number_reply("1 3 완료") == [1, 3]
    assert parse_number_reply("1,3") == [1, 3]
    assert parse_number_reply("1,3, 10") == [1, 3, 10]
    assert parse_number_reply("1, one 완료") is None
    assert parse_number_reply("이 작업 1 완료") is None
    assert parse_number_reply("0 완료") is None
    assert parse_number_reply("1, 1") is None


@patch("seosoyoung.slackbot.handlers.daily_todo.Config")
def test_number_reply_reads_one_bot_parent_and_uses_header_scope(mock_config):
    mock_config.slack.bot_user_id = "bot-1"
    mock_config.slack.team_id = "team-1"
    client = MagicMock()
    client.conversations_replies.return_value = {
        "messages": [
            {
                "user": "bot-1",
                "ts": "123.456",
                "blocks": [
                    {
                        "type": "section",
                        "block_id": "daily_todo_header:source-card:delivery-1:2",
                    },
                    {"type": "actions", "elements": []},
                ],
            }
        ]
    }
    event = {
        "text": "1, 3 완료",
        "thread_ts": "123.456",
        "channel": "channel-1",
        "user": "user-1",
        "ts": "123.789",
    }
    dependencies = {"get_user_role": MagicMock()}

    say = MagicMock()
    with patch("seosoyoung.slackbot.handlers.daily_todo._complete", return_value=True) as complete:
        handled = try_handle_number_reply(event, say, client, dependencies)

    assert handled
    client.conversations_replies.assert_called_once_with(channel="channel-1", ts="123.456", limit=1)
    complete.assert_called_once()
    assert complete.call_args.kwargs["source_card_id"] == "source-card"
    assert complete.call_args.kwargs["delivery_id"] == "delivery-1"
    assert complete.call_args.kwargs["part_index"] == 2
    assert complete.call_args.kwargs["numbers"] == [1, 3]
    say.assert_not_called()


@patch("seosoyoung.slackbot.handlers.daily_todo.Config")
def test_number_reply_does_not_claim_a_non_bot_thread(mock_config):
    mock_config.slack.bot_user_id = "bot-1"
    client = MagicMock()
    client.conversations_replies.return_value = {
        "messages": [{"user": "other-bot", "blocks": []}]
    }

    handled = try_handle_number_reply(
        {
            "text": "1 완료",
            "thread_ts": "123.456",
            "channel": "channel-1",
            "user": "user-1",
            "ts": "123.789",
        },
        MagicMock(),
        client,
        {"get_user_role": MagicMock()},
    )

    assert handled is False


@patch("seosoyoung.slackbot.handlers.daily_todo.Config")
def test_missing_number_reply_uses_one_korean_failure_message(mock_config):
    from seosoyoung.slackbot.daily_todo.completion import CompletionRejected

    mock_config.slack.bot_user_id = "bot-1"
    mock_config.slack.team_id = "team-1"
    client = MagicMock()
    client.conversations_replies.return_value = {
        "messages": [{"user": "bot-1", "ts": "123.456", "blocks": [{
            "type": "section", "block_id": "daily_todo_header:card-1:delivery-1:1"
        }]}]
    }
    event = {"text": "99 완료", "thread_ts": "123.456", "channel": "channel-1", "user": "user-1", "ts": "1793000000"}
    say = MagicMock()
    with patch("seosoyoung.slackbot.handlers.daily_todo._complete", side_effect=CompletionRejected(
        "이 메시지에 없는 번호입니다. 같은 메시지의 번호를 확인해 다시 보내주세요."
    )):
        assert try_handle_number_reply(event, say, client, {})
    say.assert_called_once_with(
        text="이 메시지에 없는 번호입니다. 같은 메시지의 번호를 확인해 다시 보내주세요.",
        thread_ts="123.456",
    )


def test_invalid_row_error_and_internal_debug_have_user_safe_messages():
    from seosoyoung.slackbot.daily_todo.parser import DailyTodoFormatError
    from seosoyoung.slackbot.handlers.daily_todo import _friendly_error
    from seosoyoung.slackbot.soulstream.debug_policy import is_user_facing_debug_message

    message = "같은 작업 행에 서로 다른 TODO ID가 연결되어 있습니다. 원문을 확인해주세요."
    assert _friendly_error(DailyTodoFormatError(message)) == message
    assert not is_user_facing_debug_message("selected number is outside this Slack message")
    assert not is_user_facing_debug_message("selected number has no saved TODO mapping")


def test_dm_number_reply_runs_before_session_cache_lookup():
    from seosoyoung.slackbot.handlers.message import _handle_dm_message

    event = {
        "subtype": None,
        "text": "1 완료",
        "thread_ts": "123.456",
        "ts": "123.789",
        "channel": "channel-1",
        "user": "user-1",
    }
    session_manager = MagicMock()
    dependencies = {
        "session_manager": session_manager,
        "restart_manager": MagicMock(is_pending=False),
        "run_claude_in_session": MagicMock(),
        "get_user_role": MagicMock(),
    }
    with patch(
        "seosoyoung.slackbot.handlers.daily_todo.try_handle_number_reply",
        return_value=True,
    ) as number_reply:
        _handle_dm_message(event, MagicMock(), MagicMock(), dependencies)

    number_reply.assert_called_once()
    session_manager.get.assert_not_called()


@patch("seosoyoung.slackbot.handlers.daily_todo.Config")
def test_button_action_payload_acks_then_saves_and_updates_message(mock_config):
    mock_config.slack.bot_user_id = EXPECTED_BOT_USER_ID
    mock_config.slack.team_id = "team-1"
    todo_id = "2026-10-27:1"
    delivery = {
        "delivery_id": "delivery-1",
        "source_card_id": "card-1",
        "date": "2026-10-27",
        "team_id": "team-1",
        "bot_user_id": EXPECTED_BOT_USER_ID,
        "recipient_user_id": EXPECTED_RECIPIENT_USER_ID,
        "channel_id": "channel-1",
        "status": "success",
        "todo_url": "https://atom.example.test/#today",
        "number_to_todo_id": {"1": todo_id},
        "parts": [{"message_ts": "123.456", "numbers": [1]}],
    }
    metadata = {
        "date": "2026-10-27",
        "slack_todo_active_delivery_id": "delivery-1",
        "slack_todo_deliveries": [delivery],
    }
    raw = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    content = (
        "## 회사일\n- **1.** 작업 — 메모 <!--todo:2026-10-27:1-->\n"
        f"<!-- daily-todo {raw} -->"
    )
    atom_card = {"id": "card-1", "version": 4, "content": content}
    order = []

    class FakeAtom:
        async def get_card(self, card_id):
            return dict(atom_card)

        async def update_card(self, card_id, *, content, expected_version):
            assert expected_version == atom_card["version"]
            order.append("atom")
            atom_card.update(version=expected_version + 1, content=content)

    class FakeApp:
        def __init__(self):
            self.handlers = []

        def action(self, pattern):
            def register(handler):
                self.handlers.append((pattern, handler))
                return handler

            return register

    class FakeSlack:
        def __init__(self):
            self.updated = []
            self.chat_postEphemeral = MagicMock()

        def chat_update(self, **kwargs):
            order.append("slack_update")
            self.updated.append(kwargs)

    app = FakeApp()
    slack = FakeSlack()
    register_daily_todo_handlers(
        app,
        {
            "get_user_role": lambda user_id, client: {
                "user_id": user_id,
                "role": "viewer",
                "is_bot": False,
            },
            "daily_todo_atom_client": FakeAtom,
        },
    )
    pattern, handler = app.handlers[0]
    assert pattern.fullmatch("daily_todo_set_completion:1")
    action_time = str(datetime(2026, 10, 27, 2, tzinfo=timezone.utc).timestamp())
    button_value = {
        "delivery_id": "delivery-1",
        "source_card_id": "card-1",
        "todo_id": todo_id,
        "number": 1,
        "target_state": "complete",
    }
    body = {
        "team": {"id": "team-1"},
        "user": {"id": EXPECTED_RECIPIENT_USER_ID},
        "channel": {"id": "channel-1"},
        "message": {
            "user": EXPECTED_BOT_USER_ID,
            "ts": "123.456",
            "blocks": [
                {
                    "type": "section",
                    "block_id": "daily_todo_header:card-1:delivery-1:1",
                },
                {"type": "actions", "elements": []},
            ],
        },
        "action_ts": "wrong-parent-time",
    }
    action = {
        "action_id": "daily_todo_set_completion:1",
        "action_ts": action_time,
        "value": json.dumps(button_value),
    }
    ack = MagicMock(side_effect=lambda: order.append("ack"))

    handler(ack, body, action, slack)

    saved = parse_daily_todo_card(atom_card["content"])
    completion_event = saved.metadata["slack_todo_completion_events"][0]
    assert order == ["ack", "atom", "slack_update"]
    assert completion_event["confirmed_at"] == datetime.fromtimestamp(
        float(action_time), timezone.utc
    ).isoformat()
    assert "- **1.** ~~작업~~ — 메모" in saved.content_before_metadata
    assert slack.updated[0]["ts"] == "123.456"
    rendered_buttons = [
        button
        for block in slack.updated[0]["blocks"]
        if block["type"] == "actions"
        for button in block["elements"]
    ]
    assert rendered_buttons[0]["action_id"] == "daily_todo_set_completion:1"
    assert rendered_buttons[0]["text"]["text"] == "↺1"
    slack.chat_postEphemeral.assert_not_called()
