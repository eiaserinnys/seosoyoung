"""Render immutable delivery snapshots with current item states."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as Date
from typing import Any, Mapping

from seosoyoung.slackbot.daily_todo.model import visible_ids
from seosoyoung.slackbot.formatting import markdown_to_mrkdwn

MAX_BLOCKS = 50
MAX_SECTION_CHARS = 3000
MAX_ACTIONS = 10
MAX_ACCESSIBILITY_LABEL_CHARS = 75
ACTION_ID_PREFIX = 'daily_todo_set_completion:'
HEADER_PREFIX = 'daily_todo_v2:'


@dataclass(frozen=True)
class RenderedDailyTodoPart:
    text: str
    blocks: list[dict[str, Any]]
    numbers: list[int]
    snapshot: list[dict[str, Any]]


def _chunks(text: str, limit: int = 2980) -> list[str]:
    chunks = []
    while len(text) > limit:
        split = text.rfind(' ', 0, limit + 1)
        if split <= 0:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _button(item: Mapping[str, Any], number: int, delivery_id: str, status: str) -> dict[str, Any]:
    target = 'reopen' if status == 'done' else 'complete'
    action = '다시 열기' if target == 'reopen' else '완료 처리'
    prefix, suffix = f'{number}번 ', f' {action}'
    title = str(item['title'])
    budget = MAX_ACCESSIBILITY_LABEL_CHARS - len(prefix) - len(suffix)
    if len(title) > budget:
        title = title[:budget - 1] + '…'
    payload = {'delivery_id': delivery_id, 'todo_id': item['id'], 'number': number, 'target_state': target}
    return {'type': 'button', 'action_id': f'{ACTION_ID_PREFIX}{number}',
            'text': {'type': 'plain_text', 'text': f'↺{number}' if target == 'reopen' else f'✓{number}'},
            'accessibility_label': prefix + title + suffix,
            'value': json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}


def _ordered(items: list[dict[str, Any]], areas: list[str], today: str) -> list[tuple[str, dict[str, Any], int]]:
    visible = visible_ids(items, today)
    children: dict[str | None, list[dict[str, Any]]] = {}
    for item in items:
        children.setdefault(item.get('parent'), []).append(item)
    for values in children.values():
        values.sort(key=lambda item: item.get('order', 0) or 0)
    names = list(dict.fromkeys([*areas, *(item.get('area', '') for item in items if item.get('area'))]))
    ordered = []
    completed = []
    def walk(item, area, depth):
        if item['id'] not in visible or item.get('area') != area:
            return
        row = (area, item, depth)
        if depth == 0 and item.get('status') == 'done' and not children.get(item['id']):
            completed.append(row)
        else:
            ordered.append(row)
            for child in children.get(item['id'], []):
                walk(child, area, depth + 1)
    for area in names:
        for item in children.get(None, []):
            walk(item, area, 0)
    return ordered + [('한 일', item, depth) for _, item, depth in completed]


def render_daily_todo_messages(items: list[dict[str, Any]], *, areas: list[str], memos: Mapping[str, str],
                               date: str, delivery_id: str, number_to_todo_id: Mapping[int | str, str],
                               todo_url: str | None = None) -> list[RenderedDailyTodoPart]:
    """Capture text and part boundaries once; later refreshes only change states."""
    date_value = Date.fromisoformat(date)
    number_by_id = {item_id: int(number) for number, item_id in number_to_todo_id.items()}
    segments = []
    blocks: list[dict[str, Any]] = []
    buttons: list[dict[str, Any]] = []
    current_area = None
    ancestors: list[dict[str, Any]] = []

    def flush():
        nonlocal blocks, buttons
        if buttons:
            blocks.append({'kind': 'actions', 'buttons': buttons})
        if blocks:
            segments.append(blocks)
        blocks, buttons = [], []

    for area, item, depth in _ordered(items, areas, date):
        if area != current_area:
            flush()
            current_area = area
            ancestors = []
            blocks.append({'kind': 'static', 'text': f'*{_escape(area)}*'})
        if len(buttons) == MAX_ACTIONS:
            flush()
            blocks.append({'kind': 'static', 'text': f'*{_escape(area)}*'})
            for ancestor in ancestors[:depth]:
                blocks.append(ancestor)
        title = _escape(str(item.get('title', '')))
        link = item.get('link')
        if link:
            title = f'<{_escape(str(link))}|{title}>'
        details = [str(item[key]) for key in ('date', 'wait') if item.get(key)]
        if details:
            title += ' (' + ' · '.join(_escape(value) for value in details) + ')'
        number = number_by_id.get(item['id'])
        prefix = '  ' * depth + '• ' + (f'*{number}.* ' if number is not None else '')
        pieces = _chunks(prefix + title)
        first = None
        for piece in pieces:
            row = {'kind': 'row', 'id': item['id'], 'text': piece, 'status': item.get('status', 'open')}
            blocks.append(row)
            if first is None:
                first = row
        ancestors = ancestors[:depth] + ([first] if first else [])
        memo = memos.get(item['id'], '')
        if memo:
            for piece in _chunks(markdown_to_mrkdwn(memo)):
                blocks.append({'kind': 'static', 'text': piece})
        if number is not None:
            buttons.append({'id': item['id'], 'number': number, 'title': str(item.get('title', '')),
                            'status': item.get('status', 'open')})
    flush()
    short = f'{date_value.month}/{date_value.day} 확인'
    link_text = f'<{todo_url}|할 일 앱>' if todo_url else '할 일 앱'
    segments.append([{'kind': 'static', 'text': f'{short}\n{link_text}\n오늘 추가하거나 바꿀 일이 있으신가요?'}])

    # A segment can span multiple parts for long memos; its buttons remain together.
    units = []
    for segment in segments:
        unit: list[dict[str, Any]] = []
        unit_chars = 0
        for entry in segment:
            size = len(entry.get('text', '')) + 20
            if unit and (len(unit) >= MAX_BLOCKS - 1 or unit_chars + size > 38000):
                units.append(unit)
                unit, unit_chars = [], 0
            unit.append(entry)
            unit_chars += size
        if unit:
            units.append(unit)
    snapshots: list[list[dict[str, Any]]] = []
    current = []
    char_count = 0
    for unit in units:
        size = sum(len(x.get('text', '')) + 20 for x in unit)
        if current and (len(current) + len(unit) > MAX_BLOCKS - 1 or char_count + size > 38000):
            snapshots.append(current)
            current, char_count = [], 0
        current.extend(unit)
        char_count += size
    if current:
        snapshots.append(current)
    by_id = {item['id']: item for item in items}
    return [render_snapshot(snapshot, by_id, delivery_id, index, include_actions=True)
            for index, snapshot in enumerate(snapshots, 1)]


def render_snapshot(snapshot: list[dict[str, Any]], items: Mapping[str, dict[str, Any]],
                    delivery_id: str, part_index: int, *, include_actions: bool) -> RenderedDailyTodoPart:
    blocks = [{'type': 'section', 'block_id': f'{HEADER_PREFIX}{delivery_id}:{part_index}',
               'text': {'type': 'mrkdwn', 'text': '*일일 TODO*'}}]
    numbers = []
    for entry in snapshot:
        if entry['kind'] == 'actions':
            numbers.extend(button['number'] for button in entry['buttons'])
            if include_actions:
                elements = []
                for button in entry['buttons']:
                    item = items.get(button['id'])
                    status = item.get('status', 'open') if item else button['status']
                    elements.append(_button(button, button['number'], delivery_id, status))
                blocks.append({'type': 'actions', 'elements': elements})
            continue
        text = entry['text']
        if entry['kind'] == 'row':
            item = items.get(entry['id'])
            status = item.get('status') if item else None
            if status == 'done':
                text = '~' + text + '~'
            elif status == 'held':
                text += ' (보류)'
            elif item is None:
                text += ' (삭제됨)'
        blocks.append({'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}})
    text = '\n'.join(block['text']['text'] for block in blocks if block['type'] == 'section')
    if len(text) > 4000:
        text = '*일일 TODO*\n할 일 앱'
    return RenderedDailyTodoPart(text, blocks, numbers, snapshot)
