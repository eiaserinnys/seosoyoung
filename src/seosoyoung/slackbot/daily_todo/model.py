"""The TODO app's item visibility and check operation."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def visible_ids(items: list[dict[str, Any]], today: str) -> set[str]:
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    by_id = {item['id']: item for item in items}
    visible = {item['id'] for item in items if item.get('status') in {'open', 'held'} or (item.get('status') == 'done' and item.get('done_on') in {today, yesterday})}
    queue = list(visible)
    while queue:
        parent = by_id[queue.pop()].get('parent')
        if parent in by_id and parent not in visible:
            visible.add(parent)
            queue.append(parent)
    return visible


def apply_check(items: list[dict[str, Any]], todo_id: str, checked: bool, today: str) -> list[dict[str, Any]]:
    """Apply the app operation, keeping an already requested state idempotent."""
    result = [dict(item) for item in items]
    by_id = {item['id']: item for item in result}
    target = by_id[todo_id]
    if (target.get('status') == 'done') == checked:
        return result
    target['status'] = 'done' if checked else 'open'
    target['done_on'] = today if checked else None
    if checked:
        queue, seen = [todo_id], {todo_id}
        while queue:
            current = queue.pop(0)
            for child in result:
                if child.get('parent') != current or child['id'] in seen:
                    continue
                seen.add(child['id'])
                queue.append(child['id'])
                if child.get('status') in {'open', 'held'}:
                    child['status'], child['done_on'] = 'done', today
    parent_id, seen = target.get('parent'), {todo_id}
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if not parent:
            break
        if checked:
            children = [item for item in result if item.get('parent') == parent_id]
            if not children or any(child.get('status') != 'done' for child in children):
                break
            parent['status'], parent['done_on'] = 'done', today
        else:
            if parent.get('status') != 'done':
                break
            parent['status'], parent['done_on'] = 'open', None
        parent_id = parent.get('parent')
    return result


def actionable_ids(items: list[dict[str, Any]]) -> set[str]:
    parents = {item.get('parent') for item in items if item.get('parent')}
    return {item['id'] for item in items if item.get('status') == 'open' and item['id'] not in parents and not item.get('context_only')}
