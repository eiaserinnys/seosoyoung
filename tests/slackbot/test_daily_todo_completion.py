import pytest

from seosoyoung.slackbot.daily_todo.completion import CompletionRejected, set_completion
from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.storage_client import StorageConflict


@pytest.fixture
def delivery_store(tmp_path):
    store = DeliveryStore(tmp_path / 'state.json')
    def setup(state):
        state['active_delivery_id'] = 'delivery'
        state['deliveries']['delivery'] = {'delivery_id': 'delivery', 'app_id': 'todo', 'status': 'success',
            'date': '2026-11-09', 'team_id': 'team', 'bot_user_id': 'bot', 'recipient_user_id': 'user',
            'channel_id': 'dm', 'number_to_todo_id': {'1': 'a', '2': 'b'},
            'parts': [{'message_ts': 'ts', 'numbers': [1, 2]}]}
    store.update(setup)
    return store


def args(**changes):
    values = dict(delivery_id='delivery', message_ts='ts', part_index=1, numbers=[1], target_state='complete',
        actual_slack_user='user', actual_team_id='team', actual_channel_id='dm', actual_bot_user_id='bot',
        confirmed_at='2026-11-08T15:30:00+00:00')
    return {**values, **changes}


@pytest.mark.asyncio
async def test_completion_cas_retries_and_keeps_unknown_fields_and_kst(fake_storage, delivery_store):
    fake_storage.conflicts = 1
    result = await set_completion(fake_storage, delivery_store, **args())
    assert result.changed and result.items[0]['done_on'] == '2026-11-09'
    assert result.items[0]['concurrent'] == 2
    assert delivery_store.read()['events'][0]['confirmed_date'] == '2026-11-09'
    result = await set_completion(fake_storage, delivery_store, **args(confirmed_at='2026-11-10T02:00:00+00:00'))
    assert not result.changed and result.items[0]['done_on'] == '2026-11-09'


@pytest.mark.asyncio
async def test_selection_rejected_together_for_missing_held_group_or_wrong_identity(fake_storage, delivery_store):
    for second in (None, {'id': 'b', 'status': 'held'}, {'id': 'b', 'status': 'open', 'context_only': True},
                   {'id': 'b', 'status': 'open'}):
        fake_storage.items = [fake_storage.items[0]] + ([second] if second else [])
        if second and second.get('context_only') is None and second['status'] == 'open':
            fake_storage.items.append({'id': 'child', 'parent': 'b', 'status': 'open'})
        with pytest.raises(CompletionRejected):
            await set_completion(fake_storage, delivery_store, **args(numbers=[1, 2]))
    with pytest.raises(CompletionRejected):
        await set_completion(fake_storage, delivery_store, **args(actual_slack_user='stranger'))
    assert fake_storage.writes == []


@pytest.mark.asyncio
async def test_second_conflict_fails_without_events(fake_storage, delivery_store):
    fake_storage.conflicts = 2
    with pytest.raises(StorageConflict):
        await set_completion(fake_storage, delivery_store, **args())
    assert delivery_store.read()['events'] == []


@pytest.mark.asyncio
async def test_part_number_identity_and_active_button_checks(fake_storage, delivery_store):
    for change in ({'numbers': [3]}, {'message_ts': 'other'}, {'actual_team_id': 'other'},
                   {'expected_number_to_todo_id': {1: 'other'}}):
        with pytest.raises(CompletionRejected):
            await set_completion(fake_storage, delivery_store, **args(**change))
    delivery_store.update(lambda s: s.update(active_delivery_id='newer'))
    with pytest.raises(CompletionRejected):
        await set_completion(fake_storage, delivery_store, **args(require_active_delivery=True))
    assert (await set_completion(fake_storage, delivery_store, **args())).changed
