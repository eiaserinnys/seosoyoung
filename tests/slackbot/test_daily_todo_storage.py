import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.storage_client import StorageClient, StorageConflict, StorageNotFound, update_items


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


def test_sequential_processes_preserve_each_others_updates(tmp_path):
    path = tmp_path / 'state.json'
    script = Path(__file__).parent / 'fixtures' / 'delivery_store_process.py'
    for value in ('first', 'second'):
        subprocess.run([sys.executable, str(script), str(path), value], check=True, timeout=10)
    assert DeliveryStore(path).read()['events'] == [{'id': 'first'}, {'id': 'second'}]
