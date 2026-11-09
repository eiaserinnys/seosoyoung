"""Allocate stable per-day numbers without reusing retired numbers."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from seosoyoung.slackbot.daily_todo.model import actionable_ids


def assign_todo_numbers(items: list[dict[str, Any]], prior: Mapping[int | str, str], next_number: int | None = None) -> dict[int, str]:
    previous = {int(number): todo_id for number, todo_id in prior.items()}
    eligible = actionable_ids(items)
    result = {number: todo_id for number, todo_id in previous.items() if todo_id in eligible}
    assigned = set(result.values())
    number = max(max(previous, default=0) + 1, next_number or 1)
    for item in items:
        todo_id = item['id']
        if todo_id in eligible and todo_id not in assigned:
            result[number] = todo_id
            assigned.add(todo_id)
            number += 1
    return result


def number_to_id_json(mapping: Mapping[int, str]) -> dict[str, str]:
    return {str(number): mapping[number] for number in sorted(mapping)}
