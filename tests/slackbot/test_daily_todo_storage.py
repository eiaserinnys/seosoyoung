import asyncio
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.publisher import (
    EXPECTED_BOT_USER_ID, EXPECTED_RECIPIENT_USER_ID, EXPECTED_TEAM_ID, publish_daily_todo,
)
from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages
from seosoyoung.slackbot.daily_todo.storage_client import StorageClient, StorageConflict, StorageNotFound, update_items
from seosoyoung.slackbot.handlers.daily_todo import _complete
from seosoyoung.slackbot.soulstream.session import SessionManager


@pytest.mark.asyncio
async def test_mcp_arguments_authentication_and_conflicts(monkeypatch):
    import fastmcp
    import fastmcp.client.transports

    calls = []
    responses = [
        SimpleNamespace(content=[SimpleNamespace(text=json.dumps({'content': [], 'revision': 'rev-1'}))], structured_content=None, is_error=False),
        SimpleNamespace(content=[SimpleNamespace(text=json.dumps({'revision': 'rev-2'}))], structured_content=None, is_error=False),
        SimpleNamespace(content=[SimpleNamespace(text=json.dumps({'id': 'STORAGE_ITEM_WRITE_CONFLICT', 'message': 'secret response'}))], structured_content=None, is_error=True),
        SimpleNamespace(content=[SimpleNamespace(text=json.dumps({'id': 'STORAGE_DOCUMENT_READ_NOT_FOUND'}))], structured_content=None, is_error=True),
    ]
    class Transport:
        def __init__(self, url, headers):
            calls.append((url, headers))
    class Client:
        def __init__(self, transport):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def call_tool(self, name, arguments, **kwargs):
            calls.append((name, arguments))
            return responses.pop(0)
    monkeypatch.setattr(fastmcp, 'Client', Client)
    monkeypatch.setattr(fastmcp.client.transports, 'StreamableHttpTransport', Transport)
    client = StorageClient(url='https://test.invalid/mcp', token='private-token')
    assert (await client.read('items'))['revision'] == 'rev-1'
    await client.write('memos', '메모', 'rev-1', doc='item-1')
    with pytest.raises(StorageConflict) as failure:
        await client.write('items', [], 'rev-2')
    assert 'private-token' not in str(failure.value)
    assert 'secret response' not in str(failure.value)
    with pytest.raises(StorageNotFound):
        await client.read('memos', doc='absent')
    assert calls[0] == ('https://test.invalid/mcp', {'Authorization': 'Bearer private-token'})
    assert calls[1] == ('read_app_storage', {'app_id': 'todo', 'entry_id': 'items'})
    assert calls[3] == ('write_app_storage', {'app_id': 'todo', 'entry_id': 'memos', 'content': '메모', 'expected_revision': 'rev-1', 'doc': 'item-1'})


@pytest.mark.asyncio
async def test_conflict_reapplies_on_latest_revision_only_once(fake_storage):
    fake_storage.conflicts = 1
    result, changed = await update_items(fake_storage, lambda items: [{**item, 'title': '변경'} for item in items])
    assert changed and result[0]['concurrent'] == 2
    assert [write[2] for write in fake_storage.writes] == ['1', '2']
    fake_storage.conflicts = 2
    with pytest.raises(StorageConflict):
        await update_items(fake_storage, lambda items: [{**item, 'title': '다시 변경'} for item in items])
    assert len(fake_storage.writes) == 4


class _BackendTransport:
    def __init__(self, url, headers):
        pass


def _structured(payload):
    return SimpleNamespace(structured_content=payload, content=[], is_error=False)


class _StorageBackend:
    """fastmcp.Client 대역. 열린 횟수를 세고 항목을 메모리에 보관한다."""

    def __init__(self, items):
        self.items = deepcopy(items)
        self.revision = 1
        self.opens = 0
        self.calls = []

    def client_class(self):
        backend = self

        class Client:
            def __init__(self, transport):
                pass

            async def __aenter__(self):
                backend.opens += 1
                return self

            async def __aexit__(self, *args):
                pass

            async def call_tool(self, name, arguments, **kwargs):
                backend.calls.append((name, arguments))
                if name == 'read_app_storage':
                    if arguments['entry_id'] == 'items':
                        return _structured({'content': deepcopy(backend.items), 'revision': str(backend.revision)})
                    if arguments['entry_id'] == 'areas':
                        return _structured({'content': ['회사일'], 'revision': None})
                    return _structured({'content': '메모', 'revision': None})
                assert name == 'write_app_storage'
                assert arguments['expected_revision'] == str(backend.revision)
                backend.items = deepcopy(arguments['content'])
                backend.revision += 1
                return _structured({'revision': str(backend.revision)})

        return Client


def _install_backend(monkeypatch, backend):
    import fastmcp
    import fastmcp.client.transports

    monkeypatch.setattr(fastmcp, 'Client', backend.client_class())
    monkeypatch.setattr(fastmcp.client.transports, 'StreamableHttpTransport', _BackendTransport)


def _role(user, _client):
    return {'user_id': user, 'is_bot': False, 'role': 'admin', 'username': 'director'}


def test_publish_opens_storage_client_once(monkeypatch, fake_slack, tmp_path):
    backend = _StorageBackend([{'id': 'a', 'title': '첫 항목', 'area': '회사일', 'parent': None,
                                'status': 'open', 'done_on': None, 'order': 0}])
    _install_backend(monkeypatch, backend)

    result = asyncio.run(publish_daily_todo(
        StorageClient(url='https://test.invalid/mcp', token='private-token'),
        DeliveryStore(tmp_path / 'state.json'),
        fake_slack,
        SessionManager(tmp_path / 'sessions'),
        date='2026-11-09',
        recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
        target_session_id='target',
        get_user_role=_role,
    ))

    assert result['status'] == 'success'
    assert backend.opens == 1


def test_completion_opens_storage_client_once(monkeypatch, tmp_path):
    item = {'id': 'a', 'title': '첫 항목', 'area': '회사일', 'parent': None,
            'status': 'open', 'done_on': None, 'order': 0}
    backend = _StorageBackend([item])
    _install_backend(monkeypatch, backend)
    part = render_daily_todo_messages([item], areas=['회사일'], memos={}, date='2026-11-09',
                                      delivery_id='delivery', number_to_todo_id={1: 'a'})[0]
    store = DeliveryStore(tmp_path / 'state.json')
    record = {'delivery_id': 'delivery', 'app_id': 'todo', 'status': 'success', 'date': '2026-11-09',
              'team_id': EXPECTED_TEAM_ID, 'bot_user_id': EXPECTED_BOT_USER_ID,
              'recipient_user_id': EXPECTED_RECIPIENT_USER_ID, 'channel_id': 'dm',
              'number_to_todo_id': {'1': 'a'},
              'parts': [{'message_ts': '123', 'numbers': [1], 'snapshot': part.snapshot}]}

    def setup(state):
        state['active_delivery_id'] = 'delivery'
        state['deliveries']['delivery'] = record

    store.update(setup)
    dependencies = {
        'daily_todo_delivery_store': store,
        'daily_todo_storage_client': lambda *, app_id: StorageClient(
            url='https://test.invalid/mcp', token='private-token', app_id=app_id),
        'get_user_role': lambda user, _client: {'user_id': user, 'is_bot': False},
    }

    assert _complete(dependencies, MagicMock(), channel_id='dm', message_ts='123',
                     delivery_id='delivery', part_index=1, numbers=[1], target_state='complete',
                     actual_user_id=EXPECTED_RECIPIENT_USER_ID, actual_team_id=EXPECTED_TEAM_ID,
                     actual_bot_user_id=EXPECTED_BOT_USER_ID,
                     confirmed_at='2026-11-09T01:00:00+00:00', is_button=False)
    assert backend.opens == 1
    assert backend.items[0]['status'] == 'done'


def test_sequential_processes_preserve_each_others_updates(tmp_path):
    path = tmp_path / 'state.json'
    script = Path(__file__).parent / 'fixtures' / 'delivery_store_process.py'
    for value in ('first', 'second'):
        subprocess.run([sys.executable, str(script), str(path), value], check=True, timeout=10)
    assert DeliveryStore(path).read()['events'] == [{'id': 'first'}, {'id': 'second'}]
