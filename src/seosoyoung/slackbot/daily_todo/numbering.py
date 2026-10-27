"""Stable per-day numbering for ID-bearing TODO rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from seosoyoung.slackbot.daily_todo.parser import TodoItem


DELIVERIES_FIELD = "slack_todo_deliveries"
ACTIVE_DELIVERY_FIELD = "slack_todo_active_delivery_id"


def read_delivery_number_map(
    metadata: Mapping[str, object], *, date: str, source_card_id: str
) -> dict[int, str]:
    """Merge immutable mappings from deliveries of this date and source card."""
    result: dict[int, str] = {}
    todo_to_number: dict[str, int] = {}
    deliveries = metadata.get(DELIVERIES_FIELD, [])
    if not isinstance(deliveries, list):
        raise ValueError(f"{DELIVERIES_FIELD} must be a list")

    for delivery in deliveries:
        if not isinstance(delivery, Mapping):
            continue
        if delivery.get("date") != date or delivery.get("source_card_id") != source_card_id:
            continue
        mapping = delivery.get("number_to_todo_id", {})
        if not isinstance(mapping, Mapping):
            raise ValueError("delivery number_to_todo_id must be an object")
        for raw_number, todo_id in mapping.items():
            number = int(raw_number)
            if number < 1 or not isinstance(todo_id, str) or not todo_id:
                raise ValueError("delivery number mapping is invalid")
            existing_id = result.get(number)
            existing_number = todo_to_number.get(todo_id)
            if existing_id is not None and existing_id != todo_id:
                raise ValueError(f"number {number} maps to multiple TODO IDs")
            if existing_number is not None and existing_number != number:
                raise ValueError(f"TODO ID {todo_id} maps to multiple numbers")
            result[number] = todo_id
            todo_to_number[todo_id] = number
    return result


def assign_todo_numbers(
    items: Sequence[TodoItem], prior_number_to_todo_id: Mapping[int | str, str]
) -> dict[int, str]:
    """Return current eligible assignments, preserving their prior numbers."""
    number_to_id: dict[int, str] = {}
    id_to_number: dict[str, int] = {}
    for raw_number, todo_id in prior_number_to_todo_id.items():
        number = int(raw_number)
        if number < 1 or not isinstance(todo_id, str) or not todo_id:
            raise ValueError("prior number mapping is invalid")
        if number in number_to_id and number_to_id[number] != todo_id:
            raise ValueError(f"number {number} maps to multiple TODO IDs")
        if todo_id in id_to_number and id_to_number[todo_id] != number:
            raise ValueError(f"TODO ID {todo_id} maps to multiple numbers")
        number_to_id[number] = todo_id
        id_to_number[todo_id] = number

    next_number = max(number_to_id, default=0) + 1
    eligible_ids = {
        item.todo_id
        for item in items
        if not item.is_completed and not item.is_group and not item.is_blocked
    }
    number_to_id = {
        number: todo_id
        for number, todo_id in number_to_id.items()
        if todo_id in eligible_ids
    }
    id_to_number = {todo_id: number for number, todo_id in number_to_id.items()}

    for item in items:
        if item.is_completed or item.is_group or item.is_blocked:
            continue
        if item.todo_id in id_to_number:
            continue
        number_to_id[next_number] = item.todo_id
        id_to_number[item.todo_id] = next_number
        next_number += 1
    return number_to_id


def number_to_id_json(mapping: Mapping[int, str]) -> dict[str, str]:
    """Use JSON object keys for persisted message-scoped numbering."""
    return {str(number): mapping[number] for number in sorted(mapping)}
