from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.publisher import (
    EXPECTED_BOT_USER_ID, EXPECTED_RECIPIENT_USER_ID, PublishRejected, main, publish_daily_todo,
)
from seosoyoung.slackbot.soulstream.session import SessionManager
def role(user, client):
    return {"user_id": user, "is_bot": False, "role": "admin", "username": "director"}


async def publish(storage, store, slack, sessions, **overrides):
    values = {'date': '2026-11-09', 'recipient_user_id': EXPECTED_RECIPIENT_USER_ID,
              'target_session_id': 'target', 'get_user_role': role}
    values.update(overrides)
    return await publish_daily_todo(storage, store, slack, sessions, **values)


@pytest.mark.asyncio
async def test_publish_records_pending_sent_success_session_and_removes_legacy_after_success(fake_storage, fake_slack, tmp_path):
    store = DeliveryStore(tmp_path / 'state.json')
    sessions = SessionManager(tmp_path / 'sessions')
    fake_slack.messages.append({'ts': 'old', 'user': EXPECTED_BOT_USER_ID, 'blocks': [
        {'type': 'section', 'block_id': 'daily_todo_header:old:old-delivery:1'},
        {'type': 'actions', 'elements': [{'action_id': 'daily_todo_set_completion:1'}, {'action_id': 'unrelated'}]}]})
    fake_storage.memos['a'] = '작업 메모'
    result = await publish(fake_storage, store, fake_slack, sessions)
    state = store.read()
    assert result['status'] == 'success' and result['session_mapping']['status'] == 'success'
    assert state['active_delivery_id'] == result['delivery_id']
    assert state['days']['2026-11-09']['number_to_todo_id'] == {'1': 'a'}
    assert fake_storage.items[0]['slack_number'] == 1
    assert fake_storage.items[0]['slack_number_date'] == '2026-11-09'
    assert state['deliveries'][result['delivery_id']]['parts'][0]['snapshot']
    assert fake_slack.updates[0]['ts'] == 'old'
    assert fake_slack.updates[0]['blocks'][1]['elements'] == [{'action_id': 'unrelated'}]
    assert sessions.get(result['parts'][0]['message_ts']).session_id == 'target'
    with pytest.raises(PublishRejected):
        await publish(fake_storage, store, fake_slack, sessions)
    with pytest.raises(PublishRejected):
        await publish(fake_storage, store, fake_slack, sessions, force=True)
    forced = await publish(fake_storage, store, fake_slack, sessions, force=True, reason='수정')
    assert forced['number_to_todo_id'] == {'1': 'a'}
    assert store.read()['deliveries'][result['delivery_id']]['status'] == 'success'


@pytest.mark.asyncio
async def test_failed_partial_send_records_parts_and_refuses_ambiguous_retry(fake_storage, fake_slack, tmp_path):
    fake_storage.items = [{**fake_storage.items[0], 'id': str(i), 'title': '할 일 ' + str(i)} for i in range(80)]
    fake_slack.fail_post_at = 2
    store = DeliveryStore(tmp_path / 'state.json')
    sessions = SessionManager(tmp_path / 'sessions')
    with pytest.raises(RuntimeError):
        await publish(fake_storage, store, fake_slack, sessions)
    saved = list(store.read()['deliveries'].values())[0]
    assert saved['status'] == 'failed' and len(saved['parts']) == 1
    with pytest.raises(PublishRejected, match='미확정 발송'):
        await publish(fake_storage, store, fake_slack, sessions)
    assert fake_slack.post_count == 2


@pytest.mark.asyncio
async def test_identity_mismatch_has_no_storage_write_or_slack_send(fake_storage, fake_slack, tmp_path):
    fake_slack.auth_test = lambda: {'team_id': 'wrong', 'user_id': EXPECTED_BOT_USER_ID, 'bot_id': 'other'}
    store = DeliveryStore(tmp_path / 'state.json')
    with pytest.raises(PublishRejected):
        await publish(fake_storage, store, fake_slack, MagicMock())
    assert fake_storage.writes == [] and fake_slack.messages == [] and not store.path.exists()


@pytest.mark.asyncio
async def test_session_failure_is_partial_not_failed_delivery(fake_storage, fake_slack, tmp_path):
    store = DeliveryStore(tmp_path / 'state.json')
    result = await publish(fake_storage, store, fake_slack, object())
    assert result['status'] == 'success'
    assert result['session_mapping']['status'] == 'partial'
    assert store.read()['deliveries'][result['delivery_id']]['status'] == 'success'


def test_preparation_command_stores_stdin_json(tmp_path, monkeypatch, capsys):
    import io
    from seosoyoung.slackbot.config import Config
    monkeypatch.setattr(Config, 'get_session_path', lambda: str(tmp_path))
    monkeypatch.setattr('sys.stdin', io.StringIO('{"prepared_at":"아침","evidence_until":"08:00"}'))
    assert main(['prepare', '--date', '2026-11-09']) == 0
    assert DeliveryStore(tmp_path / 'daily_todo' / 'state.json').read()['preparation']['2026-11-09']['prepared_at'] == '아침'
