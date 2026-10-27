from unittest.mock import MagicMock, patch

from seosoyoung.slackbot.handlers.daily_todo import parse_number_reply, try_handle_number_reply


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

    with patch("seosoyoung.slackbot.handlers.daily_todo._complete", return_value=True) as complete:
        handled = try_handle_number_reply(event, MagicMock(), client, dependencies)

    assert handled
    client.conversations_replies.assert_called_once_with(channel="channel-1", ts="123.456", limit=1)
    complete.assert_called_once()
    assert complete.call_args.kwargs["source_card_id"] == "source-card"
    assert complete.call_args.kwargs["delivery_id"] == "delivery-1"
    assert complete.call_args.kwargs["part_index"] == 2
    assert complete.call_args.kwargs["numbers"] == [1, 3]


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
