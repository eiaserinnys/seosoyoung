"""Slack button and number-reply handling for published daily TODOs."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.daily_todo.rendering import ACTION_ID_PREFIX

logger = logging.getLogger(__name__)

_NUMBER_REPLY_RE = re.compile(r"^\s*(\d+(?:[\s,]+\d+)*)\s*(?:완료)?\s*$")
_HEADER_BLOCK_RE = re.compile(r"^daily_todo_header:([^:]+):([^:]+):(\d+)$")
_ACTION_ID_RE = re.compile(rf"^{re.escape(ACTION_ID_PREFIX)}(\d+)$")


def parse_number_reply(text: str) -> list[int] | None:
    """Accept a bare list of positive numbers, optionally followed by 완료."""
    match = _NUMBER_REPLY_RE.fullmatch(text)
    if not match:
        return None
    numbers = [int(value) for value in re.findall(r"\d+", match.group(1))]
    if not numbers or any(number < 1 for number in numbers) or len(set(numbers)) != len(numbers):
        return None
    return numbers


def try_handle_number_reply(event, say, client, dependencies: dict) -> bool:
    """Resolve a number only from the bot-authored TODO parent in this thread."""
    numbers = parse_number_reply(event.get("text", ""))
    thread_ts = event.get("thread_ts")
    if numbers is None or not thread_ts:
        return False

    channel_id = event.get("channel")
    try:
        response = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=1)
        messages = response.get("messages", [])
    except Exception:
        logger.exception("TODO 번호 답장의 thread 부모 조회 실패")
        return False
    if not messages:
        return False
    parent = messages[0]
    bot_user_id = Config.slack.bot_user_id
    if not bot_user_id or parent.get("user") != bot_user_id:
        return False

    header = _todo_header(parent.get("blocks", []))
    if header is None:
        return False
    source_card_id, delivery_id, part_index = header
    try:
        return _complete(
            dependencies,
            client,
            say=say,
            thread_ts=thread_ts,
            channel_id=channel_id,
            message_ts=parent.get("ts", thread_ts),
            source_card_id=source_card_id,
            delivery_id=delivery_id,
            part_index=part_index,
            numbers=numbers,
            target_state="complete",
            actual_user_id=event.get("user", ""),
            actual_team_id=Config.slack.team_id or "",
            actual_bot_user_id=bot_user_id,
            confirmed_at=_slack_timestamp(event.get("ts")),
            is_button=False,
            reaction_ts=event.get("ts"),
        )
    except Exception as exc:
        logger.exception("TODO 번호 답장 거부")
        say(text=_friendly_error(exc), thread_ts=thread_ts)
        return True


def register_daily_todo_handlers(app, dependencies: dict) -> None:
    @app.action(_ACTION_ID_RE)
    def handle_daily_todo_action(ack, body, action, client):
        ack()
        try:
            payload = json.loads(action.get("value", ""))
            if not isinstance(payload, dict):
                raise ValueError("invalid action payload")
            action_match = _ACTION_ID_RE.fullmatch(action.get("action_id", ""))
            if not action_match or int(action_match.group(1)) != int(payload.get("number", 0)):
                raise ValueError("TODO button number does not match its action ID")
            if body.get("message", {}).get("user") != Config.slack.bot_user_id:
                raise ValueError("TODO 버튼 메시지의 봇 신원을 확인할 수 없습니다.")
            part_index = _part_index_from_action(body)
            _complete(
                dependencies,
                client,
                channel_id=body["channel"]["id"],
                message_ts=body["message"]["ts"],
                source_card_id=payload["source_card_id"],
                delivery_id=payload["delivery_id"],
                part_index=part_index,
                numbers=[int(payload["number"])],
                target_state=payload["target_state"],
                actual_user_id=body["user"]["id"],
                actual_team_id=body["team"]["id"],
                actual_bot_user_id=Config.slack.bot_user_id or "",
                confirmed_at=_slack_timestamp(action.get("action_ts")),
                is_button=True,
                expected_number_to_todo_id={payload["number"]: payload["todo_id"]},
                reaction_ts=None,
            )
        except Exception as exc:
            logger.exception("Daily TODO 버튼 처리 실패")
            _notify_failure(
                client,
                channel_id=body.get("channel", {}).get("id", ""),
                user_id=body.get("user", {}).get("id", ""),
                thread_ts=body.get("message", {}).get("ts"),
                say=None,
                is_button=True,
                text=_friendly_error(exc),
            )


def _complete(
    dependencies: dict,
    client,
    *,
    channel_id: str,
    message_ts: str,
    source_card_id: str,
    delivery_id: str,
    part_index: int,
    numbers: list[int],
    target_state: str,
    actual_user_id: str,
    actual_team_id: str,
    actual_bot_user_id: str,
    confirmed_at: str,
    is_button: bool,
    expected_number_to_todo_id: dict[int | str, str] | None = None,
    say=None,
    thread_ts: str | None = None,
    reaction_ts: str | None = None,
) -> bool:
    get_user_role = dependencies["get_user_role"]
    role = get_user_role(actual_user_id, client)
    if not role or role.get("is_bot") or role.get("user_id") != actual_user_id:
        raise ValueError("Slack 사용자 확인에 실패했습니다.")

    atom_client_factory = dependencies.get("daily_todo_atom_client")
    atom_client = atom_client_factory() if callable(atom_client_factory) else atom_client_factory
    if atom_client is None:
        raise RuntimeError("Atom TODO 클라이언트가 설정되지 않았습니다.")

    from seosoyoung.slackbot.daily_todo.completion import set_completion
    from seosoyoung.utils.async_bridge import run_in_new_loop

    outcome = run_in_new_loop(
        set_completion(
            atom_client,
            source_card_id=source_card_id,
            delivery_id=delivery_id,
            message_ts=message_ts,
            part_index=part_index,
            numbers=numbers,
            target_state=target_state,
            actual_slack_user=actual_user_id,
            actual_team_id=actual_team_id,
            actual_channel_id=channel_id,
            actual_bot_user_id=actual_bot_user_id,
            confirmed_at=confirmed_at,
            require_active_delivery=is_button,
            expected_number_to_todo_id=expected_number_to_todo_id,
        )
    )

    try:
        _refresh_messages(client, outcome, part_index, numbers)
        for related in outcome.current_refreshes:
            _refresh_delivery_messages(
                client,
                related["card"],
                related["delivery"],
                _numbers_for_todo_ids(related["delivery"], related["todo_ids"]),
                update_all=True,
            )
    except Exception:
        logger.exception("TODO Atom 반영 뒤 Slack 메시지 갱신 실패")
        _notify_failure(
            client,
            channel_id=channel_id,
            user_id=actual_user_id,
            thread_ts=thread_ts or message_ts,
            say=say,
            is_button=is_button,
            text="TODO는 반영됐지만 Slack 알림 갱신은 실패했습니다.",
        )
        return True

    if outcome.partial_error:
        _notify_failure(
            client,
            channel_id=channel_id,
            user_id=actual_user_id,
            thread_ts=thread_ts or message_ts,
            say=say,
            is_button=is_button,
            text="원래 TODO는 반영됐지만 오늘 카드로 이월된 항목 동기화는 실패했습니다.",
        )
        return True

    if not is_button:
        try:
            client.reactions_add(
                channel=channel_id,
                timestamp=reaction_ts or event_ts_from_time(confirmed_at),
                name="white_check_mark",
            )
        except Exception:
            logger.info("TODO 번호 답장에 ✅ 반응을 추가하지 못했습니다", exc_info=True)
    return True


def _refresh_messages(client, outcome, selected_part_index: int, selected_numbers: list[int]) -> None:
    _refresh_delivery_messages(client, outcome.card, outcome.delivery, selected_numbers)


def _refresh_delivery_messages(
    client,
    card: dict[str, Any],
    delivery: dict[str, Any],
    selected_numbers: list[int],
    *,
    update_all: bool = False,
) -> None:
    from seosoyoung.slackbot.daily_todo.parser import parse_daily_todo_card
    from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages

    parsed = parse_daily_todo_card(card["content"])
    active = parsed.metadata.get("slack_todo_active_delivery_id") == delivery.get("delivery_id")
    mapping = {int(number): todo_id for number, todo_id in delivery["number_to_todo_id"].items()}
    rendered = render_daily_todo_messages(
        parsed.content_before_metadata,
        metadata=parsed.metadata,
        source_card_id=delivery["source_card_id"],
        delivery_id=delivery["delivery_id"],
        number_to_todo_id=mapping,
        todo_url=delivery.get("todo_url", "https://atom.eiaserinnys.me"),
        include_actions=active,
    )
    parts = delivery.get("parts", [])
    for index, part_record in enumerate(parts, start=1):
        part_numbers = {int(number) for number in part_record.get("numbers", [])}
        if not update_all and not part_numbers.intersection(selected_numbers):
            continue
        if index > len(rendered):
            raise RuntimeError("rendered TODO part no longer matches the saved message mapping")
        part = rendered[index - 1]
        client.chat_update(
            channel=delivery["channel_id"],
            ts=part_record["message_ts"],
            text=part.text,
            blocks=part.blocks,
        )


def _numbers_for_todo_ids(delivery: dict[str, Any], todo_ids: list[str]) -> list[int]:
    wanted = set(todo_ids)
    return [
        int(number)
        for number, todo_id in delivery["number_to_todo_id"].items()
        if todo_id in wanted
    ]


def _todo_header(blocks: list[dict[str, Any]]) -> tuple[str, str, int] | None:
    for block in blocks:
        if block.get("type") == "actions":
            continue
        match = _HEADER_BLOCK_RE.fullmatch(block.get("block_id", ""))
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        return None
    return None


def _part_index_from_action(body: dict) -> int:
    header = _todo_header(body.get("message", {}).get("blocks", []))
    if header is None:
        raise ValueError("TODO 메시지 머리말을 찾을 수 없습니다.")
    return header[2]


def _slack_timestamp(value: Any) -> str:
    if value is None:
        raise ValueError("Slack action timestamp is missing")
    moment = datetime.fromtimestamp(float(value), timezone.utc)
    return moment.isoformat()


def event_ts_from_time(value: str) -> str:
    return str(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _notify_failure(client, *, channel_id: str, user_id: str, thread_ts, say, is_button: bool, text: str) -> None:
    if not channel_id:
        return
    try:
        if is_button:
            client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
        elif say:
            say(text=text, thread_ts=thread_ts)
    except Exception:
        logger.debug("TODO 실패 안내 전송 실패", exc_info=True)


def _friendly_error(exc: Exception) -> str:
    from seosoyoung.slackbot.daily_todo.completion import CompletionRejected
    from seosoyoung.slackbot.daily_todo.parser import (
        DUPLICATE_TODO_ROW_MESSAGE,
        MISSING_TODO_ROW_MESSAGE,
        DailyTodoFormatError,
    )

    if isinstance(exc, CompletionRejected):
        return str(exc)
    if isinstance(exc, DailyTodoFormatError) and str(exc) in {
        DUPLICATE_TODO_ROW_MESSAGE,
        MISSING_TODO_ROW_MESSAGE,
    }:
        return str(exc)
    return "TODO 상태를 확인하지 못했습니다. 잠시 뒤 다시 시도해주세요."

