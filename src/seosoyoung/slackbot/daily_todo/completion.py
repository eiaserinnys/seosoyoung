"""Validate a delivery and apply a single atomic item selection."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from seosoyoung.slackbot.daily_todo.model import apply_check
from seosoyoung.slackbot.daily_todo.storage_client import update_items


class CompletionRejected(ValueError):
    pass


MISSING_NUMBER_MESSAGE = '이 메시지에 없는 번호입니다. 같은 메시지의 번호를 확인해 다시 보내주세요.'


@dataclass(frozen=True)
class CompletionOutcome:
    items: list[dict[str, Any]]
    delivery: dict[str, Any]
    numbers: list[int]
    todo_ids: list[str]
    refresh_ids: set[str]
    changed: bool
    active_delivery_id: str | None
    related_deliveries: list[dict[str, Any]]


async def set_completion(storage, store, *, delivery_id: str, message_ts: str, part_index: int,
                         numbers: Sequence[int], target_state: str, actual_slack_user: str,
                         actual_team_id: str, actual_channel_id: str, actual_bot_user_id: str,
                         confirmed_at: str, require_active_delivery: bool = False,
                         expected_number_to_todo_id: Mapping[int | str, str] | None = None) -> CompletionOutcome:
    if target_state not in {'complete', 'reopen'} or not numbers:
        raise CompletionRejected('완료할 번호와 상태를 확인해 주세요.')
    selected = list(dict.fromkeys(int(number) for number in numbers))
    if any(number < 1 for number in selected):
        raise CompletionRejected(MISSING_NUMBER_MESSAGE)
    state = store.read()
    delivery = state['deliveries'].get(delivery_id)
    if not delivery or delivery.get('status') != 'success':
        raise CompletionRejected('발송 기록을 찾을 수 없습니다. 오늘 할 일 메시지를 확인해 주세요.')
    if (delivery.get('team_id') != actual_team_id or delivery.get('bot_user_id') != actual_bot_user_id
        or delivery.get('channel_id') != actual_channel_id or delivery.get('recipient_user_id') != actual_slack_user):
        raise CompletionRejected('이 메시지의 수신자와 발송 정보를 확인할 수 없습니다.')
    active = state.get('active_delivery_id')
    if require_active_delivery and active != delivery_id:
        raise CompletionRejected('이전 메시지의 버튼입니다. 오늘 할 일 메시지를 사용해 주세요.')
    parts = delivery.get('parts', [])
    if part_index < 1 or part_index > len(parts) or parts[part_index - 1].get('message_ts') != message_ts:
        raise CompletionRejected('이 메시지의 발송 기록을 확인할 수 없습니다.')
    part_numbers = {int(n) for n in parts[part_index - 1].get('numbers', [])}
    mapping = {int(number): item_id for number, item_id in delivery['number_to_todo_id'].items()}
    if any(number not in part_numbers or number not in mapping for number in selected):
        raise CompletionRejected(MISSING_NUMBER_MESSAGE)
    if expected_number_to_todo_id is not None:
        expected = {int(n): item_id for n, item_id in expected_number_to_todo_id.items()}
        if any(mapping[n] != expected.get(n) for n in selected):
            raise CompletionRejected('버튼의 할 일과 발송 기록이 다릅니다.')
    selected_ids = [mapping[number] for number in selected]
    day = datetime.fromisoformat(confirmed_at.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    checked = target_state == 'complete'
    changed_ids: set[str] = set()

    def operation(items):
        nonlocal changed_ids
        by_id = {item['id']: item for item in items}
        parents = {item.get('parent') for item in items if item.get('parent')}
        for number, item_id in zip(selected, selected_ids):
            item = by_id.get(item_id)
            if item is None:
                raise CompletionRejected(f'{number}번 할 일이 삭제되었습니다.')
            if item.get('status') == 'held' or item_id in parents or item.get('context_only'):
                raise CompletionRejected(f'{number}번은 지금 완료하거나 다시 열 수 없는 항목입니다.')
        result = items
        for item_id in selected_ids:
            result = apply_check(result, item_id, checked, day)
        changed_ids = {item['id'] for item in result
                       if (item.get('status'), item.get('done_on')) !=
                       (by_id[item['id']].get('status'), by_id[item['id']].get('done_on'))}
        return result

    _, changed = await update_items(storage, operation)
    verified = (await storage.read('items'))['content']
    by_id = {item['id']: item for item in verified}
    if any(item_id not in by_id or (by_id[item_id].get('status') == 'done') != checked for item_id in selected_ids):
        raise RuntimeError('저장된 할 일 상태를 확인하지 못했습니다.')
    if changed:
        def record(state):
            for item_id in selected_ids:
                state['events'].append({'todo_id': item_id, 'state': target_state, 'confirmed_at': confirmed_at,
                                        'confirmed_date': day, 'slack_user_id': actual_slack_user,
                                        'delivery_id': delivery_id, 'message_ts': message_ts})
        store.update(record)
    latest = store.read()
    active = latest.get('active_delivery_id')
    related = []
    refresh_ids = changed_ids | set(selected_ids)
    if active and active != delivery_id:
        other = latest['deliveries'].get(active)
        if other and any(refresh_ids & part_item_ids(part) for part in other.get('parts', [])):
            related.append(other)
    return CompletionOutcome(verified, delivery, selected, selected_ids, refresh_ids, changed, active, related)


def part_item_ids(part: Mapping[str, Any]) -> set[str]:
    ids = set()
    for entry in part.get('snapshot', []):
        if entry.get('kind') == 'row':
            ids.add(entry['id'])
        elif entry.get('kind') == 'actions':
            ids.update(button['id'] for button in entry.get('buttons', []))
    return ids
