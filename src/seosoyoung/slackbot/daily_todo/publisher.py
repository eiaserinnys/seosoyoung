"""Publish a numbered daily TODO and persist its immutable Slack mapping."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from seosoyoung.slackbot.daily_todo.atom_client import AtomMcpClient
from seosoyoung.slackbot.daily_todo.numbering import (
    ACTIVE_DELIVERY_FIELD,
    DELIVERIES_FIELD,
    assign_todo_numbers,
    number_to_id_json,
    read_delivery_number_map,
)
from seosoyoung.slackbot.daily_todo.parser import (
    DailyTodoFormatError,
    parse_daily_todo_card,
    parse_todo_items,
    replace_daily_todo_metadata,
)
from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages


logger = logging.getLogger(__name__)


class PublishRejected(ValueError):
    """A publish is missing explicit context or would replace a success."""


async def publish_daily_todo(
    atom_client,
    slack_client,
    session_manager,
    *,
    card_id: str,
    todo_node_id: str,
    recipient_user_id: str,
    target_session_id: str,
    force: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    required = (card_id, todo_node_id, recipient_user_id, target_session_id)
    if not all(required):
        raise PublishRejected("card, node, recipient and target session are required")
    if force and not (reason and reason.strip()):
        raise PublishRejected("--force requires a non-empty --reason")

    auth = slack_client.auth_test()
    team_id = auth["team_id"]
    bot_user_id = auth["user_id"]
    channel = slack_client.conversations_open(users=recipient_user_id)["channel"]["id"]
    user = slack_client.users_info(user=recipient_user_id)["user"]
    username = user.get("name", recipient_user_id)
    date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    delivery_id = str(uuid.uuid4())
    todo_url = f"https://atom.eiaserinnys.me/#{todo_node_id}"

    card = await atom_client.get_card(card_id)
    parsed = parse_daily_todo_card(card["content"])
    if parsed.metadata.get("date") != date:
        raise PublishRejected("the selected card is not today's Asia/Seoul TODO")
    _reject_successful_resend(parsed.metadata, force=force)

    card, delivery, mapping = await _save_pending_delivery(
        atom_client,
        card_id=card_id,
        delivery_id=delivery_id,
        date=date,
        team_id=team_id,
        bot_user_id=bot_user_id,
        recipient_user_id=recipient_user_id,
        channel_id=channel,
        target_session_id=target_session_id,
        todo_url=todo_url,
        reason=reason.strip() if reason and reason.strip() else None,
        force=force,
    )
    prior_active_id = delivery.get("previous_active_delivery_id")

    sent_parts: list[dict[str, Any]] = []
    try:
        parsed = parse_daily_todo_card(card["content"])
        parts = render_daily_todo_messages(
            parsed.content_before_metadata,
            metadata=parsed.metadata,
            source_card_id=card_id,
            delivery_id=delivery_id,
            number_to_todo_id=mapping,
            todo_url=todo_url,
        )
        expected_parts = []
        for part in parts:
            response = slack_client.chat_postMessage(
                channel=channel,
                text=part.text,
                blocks=part.blocks,
            )
            message_ts = response["ts"]
            sent_parts.append({"message_ts": message_ts, "numbers": part.numbers})
            expected_parts.append(part)

        _verify_posted_parts(slack_client, channel, bot_user_id, sent_parts, expected_parts, delivery_id, card_id)

        delivery = await _mark_delivery_success(
            atom_client,
            card_id=card_id,
            delivery_id=delivery_id,
            parts=sent_parts,
        )
    except Exception as exc:
        await _mark_delivery_failed(atom_client, card_id, delivery_id, str(exc), sent_parts)
        if sent_parts:
            try:
                _remove_old_daily_todo_actions(
                    slack_client,
                    {"channel_id": channel, "parts": sent_parts},
                )
            except Exception:
                logger.exception("Failed TODO delivery's partial messages could not be cleaned up")
        raise

    for part in sent_parts:
        session = session_manager.create(
            thread_ts=part["message_ts"],
            channel_id=channel,
            user_id=recipient_user_id,
            username=username,
            role="viewer",
        )
        if session:
            session_manager.update_session_id(part["message_ts"], target_session_id)

    actions_cleanup_error = None
    if prior_active_id and prior_active_id != delivery_id:
        old_delivery = _find_delivery_by_id(delivery["_metadata"], prior_active_id)
        if old_delivery:
            try:
                _remove_old_daily_todo_actions(slack_client, old_delivery)
            except Exception as exc:
                actions_cleanup_error = str(exc)
                logger.exception("New TODO delivery is active but old TODO actions cleanup failed")

    result = {
        "delivery_id": delivery_id,
        "source_card_id": card_id,
        "date": date,
        "team_id": team_id,
        "recipient_user_id": recipient_user_id,
        "channel_id": channel,
        "number_to_todo_id": number_to_id_json(mapping),
        "parts": sent_parts,
        "status": "success",
    }
    if actions_cleanup_error:
        result["old_actions_cleanup_error"] = actions_cleanup_error
    return result


async def _save_pending_delivery(
    atom_client,
    *,
    card_id: str,
    delivery_id: str,
    date: str,
    team_id: str,
    bot_user_id: str,
    recipient_user_id: str,
    channel_id: str,
    target_session_id: str,
    todo_url: str,
    reason: str | None,
    force: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[int, str]]:
    for attempt in range(2):
        card = await atom_client.get_card(card_id)
        parsed = parse_daily_todo_card(card["content"])
        if parsed.metadata.get("date") != date:
            raise PublishRejected("today's TODO card changed before publishing")
        _reject_successful_resend(parsed.metadata, force=force)
        prior = read_delivery_number_map(parsed.metadata, date=date, source_card_id=card_id)
        mapping = assign_todo_numbers(parse_todo_items(parsed.content_before_metadata), prior)
        delivery = {
            "delivery_id": delivery_id,
            "source_card_id": card_id,
            "date": date,
            "team_id": team_id,
            "bot_user_id": bot_user_id,
            "recipient_user_id": recipient_user_id,
            "channel_id": channel_id,
            "target_session_id": target_session_id,
            "todo_url": todo_url,
            "number_to_todo_id": number_to_id_json(mapping),
            "parts": [],
            "status": "pending",
            "previous_active_delivery_id": parsed.metadata.get(ACTIVE_DELIVERY_FIELD),
            "created_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        }
        if reason:
            delivery["reason"] = reason
        metadata = dict(parsed.metadata)
        deliveries = metadata.get(DELIVERIES_FIELD, [])
        if not isinstance(deliveries, list):
            raise DailyTodoFormatError(f"{DELIVERIES_FIELD} must be a list")
        metadata[DELIVERIES_FIELD] = [*deliveries, delivery]
        content = replace_daily_todo_metadata(card["content"], metadata)
        try:
            await atom_client.update_card(card_id, content=content, expected_version=card["version"])
        except Exception as exc:
            if attempt == 0 and _is_version_conflict(exc):
                continue
            raise
        verified = await atom_client.get_card(card_id)
        verified_parsed = parse_daily_todo_card(verified["content"])
        verified_delivery = _find_delivery_by_id(verified_parsed.metadata, delivery_id)
        if not verified_delivery or verified_delivery.get("status") != "pending":
            raise RuntimeError("pending TODO delivery failed Atom readback")
        return verified, verified_delivery, mapping
    raise AssertionError("unreachable")


async def _mark_delivery_success(atom_client, *, card_id: str, delivery_id: str, parts: list[dict[str, Any]]):
    for attempt in range(2):
        card = await atom_client.get_card(card_id)
        parsed = parse_daily_todo_card(card["content"])
        metadata = dict(parsed.metadata)
        deliveries = list(metadata.get(DELIVERIES_FIELD, []))
        delivery = _find_delivery_by_id(metadata, delivery_id)
        if not delivery:
            raise RuntimeError("pending TODO delivery disappeared")
        next_delivery = dict(delivery)
        next_delivery["parts"] = parts
        next_delivery["status"] = "success"
        next_delivery["sent_at"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        for index, value in enumerate(deliveries):
            if isinstance(value, Mapping) and value.get("delivery_id") == delivery_id:
                deliveries[index] = next_delivery
                break
        metadata[DELIVERIES_FIELD] = deliveries
        metadata[ACTIVE_DELIVERY_FIELD] = delivery_id
        content = replace_daily_todo_metadata(card["content"], metadata)
        try:
            await atom_client.update_card(card_id, content=content, expected_version=card["version"])
        except Exception as exc:
            if attempt == 0 and _is_version_conflict(exc):
                continue
            raise
        verified = await atom_client.get_card(card_id)
        verified_metadata = parse_daily_todo_card(verified["content"]).metadata
        verified_delivery = _find_delivery_by_id(verified_metadata, delivery_id)
        if (
            verified_metadata.get(ACTIVE_DELIVERY_FIELD) != delivery_id
            or not verified_delivery
            or verified_delivery.get("status") != "success"
            or verified_delivery.get("parts") != parts
        ):
            raise RuntimeError("successful TODO delivery failed Atom readback")
        return {**verified_delivery, "_metadata": verified_metadata}
    raise AssertionError("unreachable")


async def _mark_delivery_failed(
    atom_client,
    card_id: str,
    delivery_id: str,
    error: str,
    parts: list[dict[str, Any]],
) -> None:
    try:
        card = await atom_client.get_card(card_id)
        parsed = parse_daily_todo_card(card["content"])
        metadata = dict(parsed.metadata)
        deliveries = list(metadata.get(DELIVERIES_FIELD, []))
        for index, delivery in enumerate(deliveries):
            if isinstance(delivery, Mapping) and delivery.get("delivery_id") == delivery_id:
                failed = dict(delivery)
                failed["status"] = "failed"
                failed["error"] = error[:500]
                failed["parts"] = parts
                deliveries[index] = failed
                break
        else:
            return
        metadata[DELIVERIES_FIELD] = deliveries
        if metadata.get(ACTIVE_DELIVERY_FIELD) == delivery_id:
            previous = _find_delivery_by_id(metadata, delivery_id)
            metadata[ACTIVE_DELIVERY_FIELD] = (previous or {}).get("previous_active_delivery_id")
            if metadata[ACTIVE_DELIVERY_FIELD] is None:
                metadata.pop(ACTIVE_DELIVERY_FIELD, None)
        content = replace_daily_todo_metadata(card["content"], metadata)
        await atom_client.update_card(card_id, content=content, expected_version=card["version"])
    except Exception:
        logger.exception("Failed to record TODO publish failure; active mapping was left unchanged")


def _reject_successful_resend(metadata: Mapping[str, Any], *, force: bool) -> None:
    legacy = metadata.get("slack_delivery")
    legacy_success = isinstance(legacy, Mapping) and (
        legacy.get("ok") is True or legacy.get("status") in {"success", "verified"}
    )
    deliveries = metadata.get(DELIVERIES_FIELD, [])
    new_success = isinstance(deliveries, list) and any(
        isinstance(delivery, Mapping) and delivery.get("status") == "success"
        for delivery in deliveries
    )
    if (legacy_success or new_success) and not force:
        raise PublishRejected("a successful TODO delivery already exists; use --force --reason")


def _find_delivery_by_id(metadata: Mapping[str, Any], delivery_id: str) -> dict[str, Any] | None:
    deliveries = metadata.get(DELIVERIES_FIELD, [])
    if not isinstance(deliveries, list):
        return None
    for delivery in deliveries:
        if isinstance(delivery, Mapping) and delivery.get("delivery_id") == delivery_id:
            return dict(delivery)
    return None


def _remove_old_daily_todo_actions(slack_client, delivery: Mapping[str, Any]) -> None:
    channel = delivery.get("channel_id")
    for part in delivery.get("parts", []):
        if not isinstance(part, Mapping) or not part.get("message_ts"):
            continue
        response = slack_client.conversations_replies(
            channel=channel,
            ts=part["message_ts"],
            limit=1,
        )
        messages = response.get("messages", [])
        if not messages:
            continue
        parent = messages[0]
        blocks = parent.get("blocks", [])
        filtered = []
        for block in blocks:
            if block.get("type") != "actions":
                filtered.append(block)
                continue
            elements = [
                element
                for element in block.get("elements", [])
                if element.get("action_id") != "daily_todo_set_completion"
            ]
            if elements:
                filtered.append({**block, "elements": elements})
        if filtered != blocks:
            slack_client.chat_update(
                channel=channel,
                ts=part["message_ts"],
                text=parent.get("text", ""),
                blocks=filtered,
            )


def _verify_posted_parts(slack_client, channel, bot_user_id, records, expected_parts, delivery_id, card_id):
    if len(records) != len(expected_parts):
        raise RuntimeError("posted TODO part count does not match rendered output")
    for record, expected in zip(records, expected_parts, strict=True):
        response = slack_client.conversations_replies(
            channel=channel,
            ts=record["message_ts"],
            limit=1,
        )
        messages = response.get("messages", [])
        if not messages:
            raise RuntimeError("Slack message readback returned no TODO parent")
        message = messages[0]
        if message.get("user") != bot_user_id:
            raise RuntimeError("Slack message readback did not identify the publishing bot")
        actual_blocks = message.get("blocks", [])
        expected_header = f"daily_todo_header:{card_id}:{delivery_id}:"
        if not actual_blocks or not actual_blocks[0].get("block_id", "").startswith(expected_header):
            raise RuntimeError("Slack TODO header block failed readback")
        actual_values = [
            element.get("value")
            for block in actual_blocks
            if block.get("type") == "actions"
            for element in block.get("elements", [])
        ]
        expected_values = [
            element.get("value")
            for block in expected.blocks
            if block.get("type") == "actions"
            for element in block.get("elements", [])
        ]
        if actual_values != expected_values:
            raise RuntimeError("Slack TODO actions failed message readback")
        if len(actual_blocks) != len(expected.blocks):
            raise RuntimeError("Slack TODO block count failed message readback")


def _is_version_conflict(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return "versionconflict" in message or "version conflict" in message or "expected_version" in message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish today's Atom TODO to the Slack recipient")
    parser.add_argument("--card-id", required=True)
    parser.add_argument("--todo-node-id", required=True)
    parser.add_argument("--recipient-user-id", required=True)
    parser.add_argument("--target-session-id", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reason")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.force and not (args.reason and args.reason.strip()):
        raise SystemExit("--force requires --reason")
    from pathlib import Path

    from slack_sdk import WebClient

    from seosoyoung.slackbot.config import Config
    from seosoyoung.slackbot.soulstream.session import SessionManager

    slack = WebClient(token=Config.slack.bot_token)
    sessions = SessionManager(session_dir=Path(Config.get_session_path()))
    result = asyncio.run(
        publish_daily_todo(
            AtomMcpClient(),
            slack,
            sessions,
            card_id=args.card_id,
            todo_node_id=args.todo_node_id,
            recipient_user_id=args.recipient_user_id,
            target_session_id=args.target_session_id,
            force=args.force,
            reason=args.reason,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
