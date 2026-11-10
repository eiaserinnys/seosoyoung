"""Slack button and number-reply handling for published daily TODOs."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.daily_todo.rendering import ACTION_ID_PREFIX, HEADER_PREFIX

logger = logging.getLogger(__name__)
_NUMBER_REPLY_RE = re.compile(r'^\s*(\d+(?:[\s,]+\d+)*)\s*(?:완료)?\s*$')
_HEADER_BLOCK_RE = re.compile(r'^daily_todo_v2:([^:]+):(\d+)$')
_LEGACY_HEADER_RE = re.compile(r'^daily_todo_header:[^:]+:[^:]+:\d+$')
_ACTION_ID_RE = re.compile(rf'^{re.escape(ACTION_ID_PREFIX)}(\d+)$')


def parse_number_reply(text: str) -> list[int] | None:
    match = _NUMBER_REPLY_RE.fullmatch(text)
    if not match:
        return None
    numbers = [int(value) for value in re.findall(r'\d+', match.group(1))]
    return numbers if numbers and all(number > 0 for number in numbers) and len(set(numbers)) == len(numbers) else None


def _header_id(blocks):
    for block in blocks:
        if block.get('type') != 'actions':
            return block.get('block_id', '')
    return ''


def try_handle_number_reply(event, say, client, dependencies: dict) -> bool:
    numbers = parse_number_reply(event.get('text', ''))
    thread_ts = event.get('thread_ts')
    if numbers is None or not thread_ts:
        return False
    channel = event.get('channel')
    try:
        messages = client.conversations_replies(channel=channel, ts=thread_ts, limit=1).get('messages', [])
    except Exception:
        logger.exception('TODO 번호 답장의 thread 부모 조회 실패')
        return False
    bot = Config.slack.bot_user_id
    if not messages or not bot or messages[0].get('user') != bot:
        return False
    parent = messages[0]
    header = _header_id(parent.get('blocks', []))
    if _LEGACY_HEADER_RE.fullmatch(header):
        role = dependencies['get_user_role'](event.get('user', ''), client)
        if not role or role.get('is_bot') or role.get('user_id') != event.get('user'):
            say(text='Slack 사용자 확인에 실패했습니다.', thread_ts=thread_ts)
        else:
            say(text='전환 전 메시지입니다. 오늘 할 일 메시지에 답해 주세요', thread_ts=thread_ts)
        return True
    match = _HEADER_BLOCK_RE.fullmatch(header)
    if not match:
        return False
    try:
        return _complete(dependencies, client, say=say, thread_ts=thread_ts, channel_id=channel,
            message_ts=parent.get('ts', thread_ts), delivery_id=match.group(1), part_index=int(match.group(2)),
            numbers=numbers, target_state='complete', actual_user_id=event.get('user', ''),
            actual_team_id=Config.slack.team_id or '', actual_bot_user_id=bot,
            confirmed_at=_slack_timestamp(event.get('ts')), is_button=False, reaction_ts=event.get('ts'))
    except Exception as exc:
        logger.exception('TODO 번호 답장 거부')
        say(text=_friendly_error(exc), thread_ts=thread_ts)
        return True


def register_daily_todo_handlers(app, dependencies: dict) -> None:
    @app.action(_ACTION_ID_RE)
    def handle_daily_todo_action(ack, body, action, client):
        ack()
        try:
            payload = json.loads(action.get('value', ''))
            action_match = _ACTION_ID_RE.fullmatch(action.get('action_id', ''))
            header = _HEADER_BLOCK_RE.fullmatch(_header_id(body.get('message', {}).get('blocks', [])))
            if not isinstance(payload, dict) or not action_match or int(action_match.group(1)) != int(payload.get('number', 0)):
                raise ValueError('TODO 버튼 번호를 확인할 수 없습니다.')
            if body.get('message', {}).get('user') != Config.slack.bot_user_id or not header or header.group(1) != payload.get('delivery_id'):
                raise ValueError('TODO 버튼 메시지를 확인할 수 없습니다.')
            _complete(dependencies, client, channel_id=body['channel']['id'], message_ts=body['message']['ts'],
                delivery_id=payload['delivery_id'], part_index=int(header.group(2)), numbers=[int(payload['number'])],
                target_state=payload['target_state'], actual_user_id=body['user']['id'], actual_team_id=body['team']['id'],
                actual_bot_user_id=Config.slack.bot_user_id or '', confirmed_at=_slack_timestamp(action.get('action_ts')),
                is_button=True, expected_number_to_todo_id={payload['number']: payload['todo_id']})
        except Exception as exc:
            logger.exception('Daily TODO 버튼 처리 실패')
            _notify_failure(client, channel_id=body.get('channel', {}).get('id', ''),
                user_id=body.get('user', {}).get('id', ''), thread_ts=body.get('message', {}).get('ts'),
                say=None, is_button=True, text=_friendly_error(exc))


def _complete(dependencies: dict, client, *, channel_id: str, message_ts: str, delivery_id: str,
              part_index: int, numbers: list[int], target_state: str, actual_user_id: str, actual_team_id: str,
              actual_bot_user_id: str, confirmed_at: str, is_button: bool,
              expected_number_to_todo_id: dict[int | str, str] | None = None,
              say=None, thread_ts: str | None = None, reaction_ts: str | None = None) -> bool:
    role = dependencies['get_user_role'](actual_user_id, client)
    if not role or role.get('is_bot') or role.get('user_id') != actual_user_id:
        raise ValueError('Slack 사용자 확인에 실패했습니다.')
    store = dependencies['daily_todo_delivery_store']
    store = store() if callable(store) else store
    delivery = store.read()['deliveries'].get(delivery_id)
    if not delivery:
        from seosoyoung.slackbot.daily_todo.completion import CompletionRejected
        raise CompletionRejected('발송 기록을 찾을 수 없습니다. 오늘 할 일 메시지를 확인해 주세요.')
    factory = dependencies['daily_todo_storage_client']
    storage = factory(app_id=delivery['app_id']) if callable(factory) else factory
    from seosoyoung.slackbot.daily_todo.completion import set_completion
    from seosoyoung.utils.async_bridge import run_in_new_loop
    outcome = run_in_new_loop(set_completion(storage, store, delivery_id=delivery_id, message_ts=message_ts,
        part_index=part_index, numbers=numbers, target_state=target_state, actual_slack_user=actual_user_id,
        actual_team_id=actual_team_id, actual_channel_id=channel_id, actual_bot_user_id=actual_bot_user_id,
        confirmed_at=confirmed_at, require_active_delivery=is_button,
        expected_number_to_todo_id=expected_number_to_todo_id))
    try:
        _refresh_delivery_messages(client, outcome.items, outcome.delivery, outcome.refresh_ids,
                                   active=outcome.active_delivery_id == delivery_id)
        for related in outcome.related_deliveries:
            _refresh_delivery_messages(client, outcome.items, related, outcome.refresh_ids, active=True)
    except Exception:
        logger.exception('TODO 저장 뒤 Slack 메시지 갱신 실패')
        _notify_failure(client, channel_id=channel_id, user_id=actual_user_id,
            thread_ts=thread_ts or message_ts, say=say, is_button=is_button,
            text='TODO는 반영됐지만 Slack 알림 갱신은 실패했습니다.')
        return True
    if not is_button:
        try:
            client.reactions_add(channel=channel_id, timestamp=reaction_ts or event_ts_from_time(confirmed_at), name='white_check_mark')
        except Exception:
            logger.info('TODO 번호 답장에 반응을 추가하지 못했습니다', exc_info=True)
    return True


def _refresh_delivery_messages(client, items, delivery, todo_ids, *, active):
    from seosoyoung.slackbot.daily_todo.completion import part_item_ids
    from seosoyoung.slackbot.daily_todo.rendering import render_snapshot
    by_id = {item['id']: item for item in items}
    wanted = set(todo_ids)
    for index, part in enumerate(delivery['parts'], 1):
        part_ids = part_item_ids(part)
        if not wanted.intersection(part_ids):
            continue
        rendered = render_snapshot(part['snapshot'], by_id, delivery['delivery_id'], index, include_actions=active)
        client.chat_update(channel=delivery['channel_id'], ts=part['message_ts'], text=rendered.text, blocks=rendered.blocks)


def _slack_timestamp(value: Any) -> str:
    if value is None:
        raise ValueError('Slack action timestamp is missing')
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat()


def event_ts_from_time(value: str) -> str:
    return str(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())


def _notify_failure(client, *, channel_id: str, user_id: str, thread_ts, say, is_button: bool, text: str) -> None:
    if not channel_id:
        return
    try:
        if is_button:
            client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
        elif say:
            say(text=text, thread_ts=thread_ts)
    except Exception:
        logger.debug('TODO 실패 안내 전송 실패', exc_info=True)


def _friendly_error(exc: Exception) -> str:
    from seosoyoung.slackbot.daily_todo.completion import CompletionRejected
    from seosoyoung.slackbot.daily_todo.storage_client import StorageConflict, StorageError
    if isinstance(exc, CompletionRejected):
        return str(exc)
    if isinstance(exc, StorageConflict):
        return '다른 변경과 충돌해 할 일을 저장하지 못했습니다. 다시 시도해 주세요.'
    if isinstance(exc, StorageError):
        return '할 일 저장소에 접근하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
    return 'TODO 상태를 확인하지 못했습니다. 잠시 뒤 다시 시도해주세요.'
