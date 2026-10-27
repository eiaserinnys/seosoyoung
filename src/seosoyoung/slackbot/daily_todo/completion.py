"""Idempotent TODO state changes and immutable delivery-scope validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from seosoyoung.slackbot.daily_todo.numbering import (
    ACTIVE_DELIVERY_FIELD,
    DELIVERIES_FIELD,
)
from seosoyoung.slackbot.daily_todo.parser import (
    DailyTodoFormatError,
    parse_daily_todo_card,
    parse_todo_items,
    replace_daily_todo_metadata,
    set_task_completion,
)


class CompletionRejected(ValueError):
    """The request is outside its recorded delivery or is not actionable."""


MISSING_NUMBER_MESSAGE = "이 메시지에 없는 번호입니다. 같은 메시지의 번호를 확인해 다시 보내주세요."


@dataclass(frozen=True)
class CompletionOutcome:
    card: dict[str, Any]
    delivery: dict[str, Any]
    numbers: list[int]
    todo_ids: list[str]
    changed: bool
    current_refreshes: list[dict[str, Any]]
    partial_error: str | None


async def set_completion(
    atom_client,
    *,
    source_card_id: str,
    delivery_id: str,
    message_ts: str,
    part_index: int,
    numbers: Sequence[int],
    target_state: str,
    actual_slack_user: str,
    actual_team_id: str,
    actual_channel_id: str,
    actual_bot_user_id: str,
    confirmed_at: str,
    require_active_delivery: bool = False,
    expected_number_to_todo_id: Mapping[int | str, str] | None = None,
) -> CompletionOutcome:
    """Validate the whole selection, CAS only selected rows, and re-read Atom."""
    if target_state not in {"complete", "reopen"}:
        raise CompletionRejected("target state must be complete or reopen")
    if not numbers:
        raise CompletionRejected("select at least one TODO number")
    selected = list(dict.fromkeys(int(number) for number in numbers))
    if any(number < 1 for number in selected):
        raise CompletionRejected("TODO numbers must be positive")

    changed_ids: list[str] = []
    selected_ids: list[str] = []
    for attempt in range(2):
        card = await atom_client.get_card(source_card_id)
        parsed = parse_daily_todo_card(card["content"])
        delivery = _find_delivery(parsed.metadata, source_card_id, delivery_id)
        _validate_delivery(
            delivery,
            selected,
            message_ts=message_ts,
            part_index=part_index,
            actual_slack_user=actual_slack_user,
            actual_team_id=actual_team_id,
            actual_channel_id=actual_channel_id,
            actual_bot_user_id=actual_bot_user_id,
            require_active=require_active_delivery,
            active_delivery_id=parsed.metadata.get(ACTIVE_DELIVERY_FIELD),
        )

        number_to_id = _delivery_number_map(delivery)
        if any(number not in number_to_id for number in selected):
            raise CompletionRejected(MISSING_NUMBER_MESSAGE)
        if expected_number_to_todo_id is not None:
            expected = {int(number): todo_id for number, todo_id in expected_number_to_todo_id.items()}
            if any(number_to_id[number] != expected.get(number) for number in selected):
                raise CompletionRejected("button TODO ID does not match the saved number mapping")
        selected_ids = [number_to_id[number] for number in selected]
        items = {item.todo_id: item for item in parse_todo_items(parsed.content_before_metadata)}
        for todo_id in selected_ids:
            item = items.get(todo_id)
            if item is None:
                raise CompletionRejected(f"TODO {todo_id} is no longer present on its source card")
            if item.is_group or item.is_blocked:
                raise CompletionRejected(
                    f"TODO number {number_to_id_inv(number_to_id, todo_id)} is not actionable"
                )

        next_content = parsed.content
        changed_ids = []
        confirmed_date, annotation = _completion_annotation(confirmed_at)
        for todo_id in selected_ids:
            item = items[todo_id]
            should_complete = target_state == "complete"
            if item.is_completed == should_complete:
                continue
            row_annotation = (
                annotation
                if should_complete
                else _existing_completion_annotation(parsed.content, item.line_index)
            )
            next_content = set_task_completion(
                next_content,
                todo_id,
                completed=should_complete,
                annotation=row_annotation,
            )
            changed_ids.append(todo_id)

        if not changed_ids:
            break

        metadata = dict(parsed.metadata)
        events = metadata.get("slack_todo_completion_events", [])
        if not isinstance(events, list):
            raise DailyTodoFormatError("slack_todo_completion_events must be a list")
        for todo_id in changed_ids:
            event = {
                "todo_id": todo_id,
                "state": target_state,
                "confirmed_at": confirmed_at,
                "confirmed_date": confirmed_date,
                "slack_user_id": actual_slack_user,
                "source_card_id": source_card_id,
                "delivery_id": delivery_id,
                "message_ts": message_ts,
            }
            if target_state == "complete":
                event["actual_completed_date"] = None
            events.append(event)
        metadata["slack_todo_completion_events"] = events
        next_content = replace_daily_todo_metadata(next_content, metadata)
        try:
            await atom_client.update_card(
                source_card_id,
                content=next_content,
                expected_version=card["version"],
            )
        except Exception as exc:
            if attempt == 0 and _is_version_conflict(exc):
                continue
            raise
        break

    verified = await atom_client.get_card(source_card_id)
    verified_parsed = parse_daily_todo_card(verified["content"])
    verified_delivery = _find_delivery(verified_parsed.metadata, source_card_id, delivery_id)
    verified_items = {item.todo_id: item for item in parse_todo_items(verified_parsed.content_before_metadata)}
    for todo_id in selected_ids:
        if todo_id not in verified_items:
            raise CompletionRejected(f"TODO {todo_id} disappeared during update")
        if verified_items[todo_id].is_completed != (target_state == "complete"):
            raise RuntimeError("Atom saved but the selected TODO state failed readback")
    current_refreshes: list[dict[str, Any]] = []
    partial_error = None
    source_date = verified_parsed.metadata.get("date")
    if source_date != confirmed_date and hasattr(atom_client, "search_cards"):
        try:
            current_card = await _find_today_card(atom_client, selected_ids, confirmed_date, source_card_id)
            if current_card:
                updated_current = await _update_carried_rows(
                    atom_client,
                    current_card["id"],
                    selected_ids,
                    target_state=target_state,
                    confirmed_at=confirmed_at,
                    actor=actual_slack_user,
                    original_card_id=source_card_id,
                    delivery_id=delivery_id,
                    message_ts=message_ts,
                )
                if updated_current:
                    current_metadata = parse_daily_todo_card(updated_current["content"]).metadata
                    active_id = current_metadata.get(ACTIVE_DELIVERY_FIELD)
                    current_delivery = _find_delivery_by_id(current_metadata, active_id) if active_id else None
                    if current_delivery and current_delivery.get("status") == "success":
                        current_refreshes.append(
                            {"card": updated_current, "delivery": current_delivery, "todo_ids": selected_ids}
                        )
        except Exception as exc:
            partial_error = f"오늘 TODO 동기화 실패: {exc}"
    return CompletionOutcome(
        card=verified,
        delivery=verified_delivery,
        numbers=selected,
        todo_ids=selected_ids,
        changed=bool(changed_ids),
        current_refreshes=current_refreshes,
        partial_error=partial_error,
    )


def _find_delivery(metadata: Mapping[str, Any], source_card_id: str, delivery_id: str) -> dict[str, Any]:
    deliveries = metadata.get(DELIVERIES_FIELD, [])
    if not isinstance(deliveries, list):
        raise CompletionRejected("delivery history is invalid")
    for value in deliveries:
        if (
            isinstance(value, Mapping)
            and value.get("delivery_id") == delivery_id
            and value.get("source_card_id") == source_card_id
        ):
            if value.get("status") != "success":
                raise CompletionRejected("this Slack message has no successful delivery mapping")
            return dict(value)
    raise CompletionRejected("this Slack message has no canonical TODO mapping")


def _find_delivery_by_id(metadata: Mapping[str, Any], delivery_id: str) -> dict[str, Any] | None:
    deliveries = metadata.get(DELIVERIES_FIELD, [])
    if not isinstance(deliveries, list):
        return None
    for value in deliveries:
        if isinstance(value, Mapping) and value.get("delivery_id") == delivery_id:
            return dict(value)
    return None


def _validate_delivery(
    delivery: Mapping[str, Any],
    numbers: Sequence[int],
    *,
    message_ts: str,
    part_index: int,
    actual_slack_user: str,
    actual_team_id: str,
    actual_channel_id: str,
    actual_bot_user_id: str,
    require_active: bool,
    active_delivery_id: Any,
) -> None:
    if delivery.get("team_id") != actual_team_id:
        raise CompletionRejected("this message belongs to another Slack team")
    if delivery.get("recipient_user_id") != actual_slack_user:
        raise CompletionRejected("only the configured recipient can change this TODO")
    if delivery.get("channel_id") != actual_channel_id:
        raise CompletionRejected("this message belongs to another Slack channel")
    if delivery.get("bot_user_id") != actual_bot_user_id:
        raise CompletionRejected("this TODO message was not sent by this bot")
    if require_active and active_delivery_id != delivery.get("delivery_id"):
        raise CompletionRejected("this TODO button belongs to an older delivery")
    parts = delivery.get("parts")
    if not isinstance(parts, list):
        raise CompletionRejected("delivery message mapping is invalid")
    if part_index < 1 or part_index > len(parts):
        raise CompletionRejected("TODO message part index is invalid")
    part = parts[part_index - 1]
    if not isinstance(part, Mapping) or part.get("message_ts") != message_ts:
        raise CompletionRejected("this Slack message is not the recorded TODO part")
    try:
        part_numbers = {int(number) for number in part.get("numbers", [])}
    except (TypeError, ValueError) as exc:
        raise CompletionRejected("delivery part numbering is invalid") from exc
    if not set(numbers).issubset(part_numbers):
        raise CompletionRejected(MISSING_NUMBER_MESSAGE)


def _delivery_number_map(delivery: Mapping[str, Any]) -> dict[int, str]:
    raw = delivery.get("number_to_todo_id")
    if not isinstance(raw, Mapping):
        raise CompletionRejected("delivery number mapping is invalid")
    result: dict[int, str] = {}
    for number, todo_id in raw.items():
        try:
            parsed_number = int(number)
        except (TypeError, ValueError) as exc:
            raise CompletionRejected("delivery number mapping is invalid") from exc
        if parsed_number < 1 or not isinstance(todo_id, str) or not todo_id:
            raise CompletionRejected("delivery number mapping is invalid")
        result[parsed_number] = todo_id
    return result


def _is_version_conflict(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "versionconflict" in text or "version conflict" in text or "expected_version" in text


def _completion_annotation(confirmed_at: str) -> tuple[str, str]:
    value = confirmed_at.replace("Z", "+00:00")
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(ZoneInfo("Asia/Seoul"))
    date = local.date().isoformat()
    return date, f"{local.month}/{local.day} 완료 확인"


def _existing_completion_annotation(content: str, line_index: int) -> str:
    lines = content.splitlines()
    if line_index >= len(lines):
        return ""
    match = re.search(r"\((\d{1,2}/\d{1,2} 완료 확인)\)(?=\s*(?:<!--todo:|$))", lines[line_index])
    return match.group(1) if match else ""


def number_to_id_inv(mapping: Mapping[int, str], todo_id: str) -> int:
    return next(number for number, value in mapping.items() if value == todo_id)


async def _find_today_card(atom_client, todo_ids: Sequence[str], date: str, source_card_id: str):
    found: set[str] = set()
    for todo_id in todo_ids:
        candidates = await atom_client.search_cards(f'"{todo_id}"', limit=10)
        for candidate in candidates:
            candidate_id = candidate.get("id") or candidate.get("card_id")
            if not candidate_id or candidate_id == source_card_id or candidate_id in found:
                continue
            found.add(candidate_id)
            card = await atom_client.get_card(candidate_id)
            try:
                parsed = parse_daily_todo_card(card["content"])
            except DailyTodoFormatError:
                continue
            if parsed.metadata.get("date") == date:
                card_items = {item.todo_id for item in parse_todo_items(parsed.content_before_metadata)}
                if todo_id in card_items:
                    return card
    return None


async def _update_carried_rows(
    atom_client,
    card_id: str,
    todo_ids: Sequence[str],
    *,
    target_state: str,
    confirmed_at: str,
    actor: str,
    original_card_id: str,
    delivery_id: str,
    message_ts: str,
):
    target_completed = target_state == "complete"
    confirmed_date, annotation = _completion_annotation(confirmed_at)
    for attempt in range(2):
        card = await atom_client.get_card(card_id)
        parsed = parse_daily_todo_card(card["content"])
        items = {item.todo_id: item for item in parse_todo_items(parsed.content_before_metadata)}
        if any(
            todo_id in items and (items[todo_id].is_group or items[todo_id].is_blocked)
            for todo_id in todo_ids
        ):
            raise CompletionRejected("a carried TODO is now a group, blocked, or cancelled row")
        update_ids = [
            todo_id
            for todo_id in todo_ids
            if todo_id in items
            and items[todo_id].is_completed != target_completed
        ]
        if not update_ids:
            return card
        content = parsed.content
        for todo_id in update_ids:
            item = items[todo_id]
            marker = (
                annotation
                if target_completed
                else _existing_completion_annotation(parsed.content, item.line_index)
            )
            content = set_task_completion(
                content,
                todo_id,
                completed=target_completed,
                annotation=marker,
            )
        metadata = dict(parsed.metadata)
        events = metadata.get("slack_todo_completion_events", [])
        if not isinstance(events, list):
            raise DailyTodoFormatError("slack_todo_completion_events must be a list")
        for todo_id in update_ids:
            event = {
                "todo_id": todo_id,
                "state": target_state,
                "confirmed_at": confirmed_at,
                "confirmed_date": confirmed_date,
                "slack_user_id": actor,
                "source_card_id": original_card_id,
                "delivery_id": delivery_id,
                "message_ts": message_ts,
            }
            if target_completed:
                event["actual_completed_date"] = None
            events.append(event)
        metadata["slack_todo_completion_events"] = events
        content = replace_daily_todo_metadata(content, metadata)
        try:
            await atom_client.update_card(card_id, content=content, expected_version=card["version"])
        except Exception as exc:
            if attempt == 0 and _is_version_conflict(exc):
                continue
            raise
        verified = await atom_client.get_card(card_id)
        verified_content = parse_daily_todo_card(verified["content"]).content_before_metadata
        final_items = {item.todo_id: item for item in parse_todo_items(verified_content)}
        if any(final_items[todo_id].is_completed != target_completed for todo_id in update_ids):
            raise RuntimeError("carried TODO state failed Atom readback")
        return verified
    raise AssertionError("unreachable")
