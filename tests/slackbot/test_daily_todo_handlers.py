from unittest.mock import MagicMock, patch
import json

from seosoyoung.slackbot.handlers.daily_todo import parse_number_reply, register_daily_todo_handlers, try_handle_number_reply
from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages


def test_number_reply_parser_accepts_only_number_lists():
    assert parse_number_reply('1, 3 완료') == [1, 3]
    assert parse_number_reply('1 3 완료') == [1, 3]
    assert parse_number_reply('1,3, 10') == [1, 3, 10]
    for value in ('1, one 완료', '이 작업 1 완료', '0 완료', '1, 1'):
        assert parse_number_reply(value) is None


def test_legacy_reply_responds_once_without_storage_write():
    client, say = MagicMock(), MagicMock()
    client.conversations_replies.return_value = {'messages': [{'user': 'bot', 'ts': '123', 'blocks': [
        {'type': 'section', 'block_id': 'daily_todo_header:old-card:old-delivery:1'}]}]}
    event = {'text': '1 완료', 'thread_ts': '123', 'channel': 'dm', 'user': 'real', 'ts': '1793000000'}
    dependencies = {'get_user_role': lambda user, _: {'user_id': user, 'is_bot': False},
                    'daily_todo_storage_client': MagicMock(), 'daily_todo_delivery_store': MagicMock()}
    with patch('seosoyoung.slackbot.handlers.daily_todo.Config') as config:
        config.slack.bot_user_id = 'bot'
        assert try_handle_number_reply(event, say, client, dependencies)
    say.assert_called_once_with(text='전환 전 메시지입니다. 오늘 할 일 메시지에 답해 주세요', thread_ts='123')
    dependencies['daily_todo_storage_client'].assert_not_called()
    dependencies['daily_todo_delivery_store'].assert_not_called()


def test_regular_conversation_and_non_bot_parent_are_not_claimed():
    client = MagicMock()
    client.conversations_replies.return_value = {'messages': [{'user': 'someone-else', 'blocks': []}]}
    with patch('seosoyoung.slackbot.handlers.daily_todo.Config') as config:
        config.slack.bot_user_id = 'bot'
        assert not try_handle_number_reply({'text': '대화', 'thread_ts': '1'}, MagicMock(), client, {})
        assert not try_handle_number_reply({'text': '1', 'thread_ts': '1'}, MagicMock(), client, {})


def test_dm_number_reply_runs_before_session_cache_lookup():
    from seosoyoung.slackbot.handlers.message import _handle_dm_message
    event = {'subtype': None, 'text': '1 완료', 'thread_ts': '123', 'ts': '124', 'channel': 'dm', 'user': 'user'}
    manager = MagicMock()
    dependencies = {'session_manager': manager, 'restart_manager': MagicMock(is_pending=False), 'run_claude_in_session': MagicMock(), 'get_user_role': MagicMock()}
    with patch('seosoyoung.slackbot.handlers.daily_todo.try_handle_number_reply', return_value=True):
        _handle_dm_message(event, MagicMock(), MagicMock(), dependencies)
    manager.get.assert_not_called()


def test_button_ack_identity_completion_and_refresh(fake_storage, tmp_path):
    store = DeliveryStore(tmp_path / 'state.json')
    item = fake_storage.items[0]
    part = render_daily_todo_messages([item], areas=['회사일'], memos={}, date='2026-11-09', delivery_id='delivery', number_to_todo_id={1: 'a'})[0]
    record = {'delivery_id': 'delivery', 'app_id': 'todo', 'status': 'success', 'date': '2026-11-09',
              'team_id': 'team', 'bot_user_id': 'bot', 'recipient_user_id': 'user', 'channel_id': 'dm',
              'number_to_todo_id': {'1': 'a'}, 'parts': [{'message_ts': '123', 'numbers': [1], 'snapshot': part.snapshot}]}
    def setup(state):
        state['active_delivery_id'] = 'delivery'
        state['deliveries']['delivery'] = record
    store.update(setup)
    handler = []
    app = MagicMock()
    app.action.side_effect = lambda pattern: lambda func: handler.append(func)
    deps = {'daily_todo_delivery_store': store, 'daily_todo_storage_client': fake_storage,
            'get_user_role': lambda user, client: {'user_id': user, 'is_bot': False}}
    register_daily_todo_handlers(app, deps)
    button = next(block for block in part.blocks if block['type'] == 'actions')['elements'][0]
    action = {**button, 'action_ts': '1794200000'}
    body = {'channel': {'id': 'dm'}, 'message': {'ts': '123', 'user': 'bot', 'blocks': part.blocks},
            'team': {'id': 'team'}, 'user': {'id': 'user'}}
    ack, client = MagicMock(), MagicMock()
    with patch('seosoyoung.slackbot.handlers.daily_todo.Config') as config:
        config.slack.bot_user_id = 'bot'
        handler[0](ack, body, action, client)
    ack.assert_called_once()
    assert fake_storage.items[0]['status'] == 'done'
    client.chat_update.assert_called_once()
    assert '↺1' in str(client.chat_update.call_args.kwargs['blocks'])
