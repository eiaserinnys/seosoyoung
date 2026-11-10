"""Publish daily TODO messages and keep their numbering in a local state file."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import date as Date, datetime, time as Time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore
from seosoyoung.slackbot.daily_todo.model import visible_ids
from seosoyoung.slackbot.daily_todo.numbering import assign_todo_numbers, number_to_id_json
from seosoyoung.slackbot.daily_todo.rendering import ACTION_ID_PREFIX, HEADER_PREFIX, render_daily_todo_messages
from seosoyoung.slackbot.daily_todo.storage_client import StorageClient, StorageNotFound, update_items

logger = logging.getLogger(__name__)
EXPECTED_TEAM_ID = 'T08JMN15Q01'
EXPECTED_BOT_USER_ID = 'U0A8XJZ6Q5S'
EXPECTED_BOT_ID = 'B0A8U1860D8'
EXPECTED_RECIPIENT_USER_ID = 'U08HWT0C6K1'
LEGACY_HEADER = re.compile(r'^daily_todo_header:[^:]+:[^:]+:\d+$')
KST = ZoneInfo('Asia/Seoul')
# Every successful send strips the buttons of earlier sends, so only recent messages can still carry them.
CLEANUP_LOOKBACK = timedelta(days=7)
# An unconfirmed send posts its messages after its record is created; allow for clock skew.
RETRY_LOOKBACK_MARGIN = timedelta(minutes=10)


class PublishRejected(ValueError):
    pass


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit('@', 1)[-1], parsed.path, '', ''))


def _history(client, channel: str, oldest: datetime) -> list[dict[str, Any]]:
    """Read the DM history back to `oldest` only; the full DM history is large and slow to fetch."""
    messages = []
    cursor = None
    while True:
        kwargs = {'channel': channel, 'limit': 100, 'oldest': f'{oldest.timestamp():.6f}'}
        if cursor:
            kwargs['cursor'] = cursor
        response = client.conversations_history(**kwargs)
        messages.extend(response.get('messages', []))
        cursor = response.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            return messages


def _header(message: dict[str, Any]) -> str:
    for block in message.get('blocks', []):
        if block.get('type') != 'actions':
            return block.get('block_id', '')
    return ''


def _created_at(delivery: dict[str, Any], day: str) -> datetime:
    try:
        return datetime.fromisoformat(delivery['created_at'])
    except (KeyError, TypeError, ValueError):
        return datetime.combine(Date.fromisoformat(day), Time.min, KST)


def _assert_retry_safe(state, slack, channel, day):
    candidates = [value for value in state['deliveries'].values()
                  if value.get('date') == day and value.get('status') in {'pending', 'failed'}]
    if not candidates:
        return
    messages = _history(slack, channel, min(_created_at(item, day) for item in candidates) - RETRY_LOOKBACK_MARGIN)
    headers = [_header(message) for message in messages if message.get('user') == EXPECTED_BOT_USER_ID]
    if any(any(header.startswith(f"{HEADER_PREFIX}{item['delivery_id']}:") for header in headers)
           for item in candidates):
        raise PublishRejected('미확정 발송의 메시지가 Slack에 있습니다. 발송 기록을 먼저 확인해 주세요.')
    if any(item.get('status') == 'pending' for item in candidates):
        raise PublishRejected('진행 중인 발송이 있습니다. 발송 기록을 먼저 확인해 주세요.')


async def publish_daily_todo(storage, store, slack_client, session_manager, *, date: str,
                             recipient_user_id: str, target_session_id: str, get_user_role,
                             todo_url: str | None = None, force: bool = False,
                             reason: str | None = None) -> dict[str, Any]:
    Date.fromisoformat(date)
    if not date or not recipient_user_id or not target_session_id:
        raise PublishRejected('날짜, 수신자와 대상 세션이 필요합니다.')
    if force and not (reason and reason.strip()):
        raise PublishRejected('--force requires a non-empty --reason')
    if recipient_user_id != EXPECTED_RECIPIENT_USER_ID:
        raise PublishRejected('daily TODO recipient must be the configured company director')
    auth = slack_client.auth_test()
    if (auth.get('team_id'), auth.get('user_id'), auth.get('bot_id')) != (EXPECTED_TEAM_ID, EXPECTED_BOT_USER_ID, EXPECTED_BOT_ID):
        raise PublishRejected('Slack team or bot identity does not match the configured company bot')
    role = get_user_role(recipient_user_id, slack_client)
    if not role or role.get('user_id') != recipient_user_id or role.get('is_bot') or role.get('role') not in {'admin', 'viewer'}:
        raise PublishRejected('configured Slack recipient identity could not be verified')
    channel = slack_client.conversations_open(users=recipient_user_id)['channel']['id']
    existing = store.read()
    if not force and any(d.get('date') == date and d.get('recipient_user_id') == recipient_user_id and d.get('team_id') == EXPECTED_TEAM_ID and d.get('status') == 'success' for d in existing['deliveries'].values()):
        raise PublishRejected('a successful TODO delivery already exists; use --force --reason')
    _assert_retry_safe(existing, slack_client, channel, date)
    initial = (await storage.read('items'))['content']
    delivery_id = str(uuid.uuid4())
    app_id = storage.app_id

    def reserve(state):
        deliveries = state['deliveries']
        storage_identity = {'server': _safe_url(storage.url), 'app_id': app_id}
        if state.get('storage') and state['storage'] != storage_identity:
            raise PublishRejected('발송 기록의 할 일 저장소가 현재 설정과 다릅니다.')
        if any(d.get('date') == date and d.get('status') == 'pending' for d in deliveries.values()):
            raise PublishRejected('진행 중인 발송이 있습니다. 발송 기록을 먼저 확인해 주세요.')
        if not force and any(d.get('date') == date and d.get('recipient_user_id') == recipient_user_id and d.get('team_id') == EXPECTED_TEAM_ID and d.get('status') == 'success' for d in deliveries.values()):
            raise PublishRejected('a successful TODO delivery already exists; use --force --reason')
        day = state['days'].setdefault(date, {'number_to_todo_id': {}, 'next_number': 1, 'active_delivery_id': None})
        mapping = assign_todo_numbers(initial, day['number_to_todo_id'], day['next_number'])
        day['number_to_todo_id'].update(number_to_id_json(mapping))
        day['next_number'] = max(day['next_number'], max(mapping, default=0) + 1)
        state.setdefault('transition_date', date)
        state.setdefault('storage', storage_identity)
        delivery = {'delivery_id': delivery_id, 'app_id': app_id, 'date': date,
                    'team_id': EXPECTED_TEAM_ID, 'bot_user_id': EXPECTED_BOT_USER_ID,
                    'recipient_user_id': recipient_user_id, 'channel_id': channel,
                    'target_session_id': target_session_id, 'todo_url': todo_url,
                    'number_to_todo_id': number_to_id_json(mapping), 'parts': [], 'status': 'pending',
                    'previous_active_delivery_id': state.get('active_delivery_id'),
                    'created_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat()}
        if reason and reason.strip():
            delivery['reason'] = reason.strip()
        deliveries[delivery_id] = delivery
        return dict(delivery), mapping

    delivery, mapping = store.update(reserve)
    sent = []
    marked_success = False
    try:
        numbers_by_id = {item_id: number for number, item_id in mapping.items()}
        def set_numbers(items):
            result = [dict(item) for item in items]
            for item in result:
                if item['id'] in numbers_by_id:
                    item['slack_number'] = numbers_by_id[item['id']]
                    item['slack_number_date'] = date
                elif item.get('slack_number_date') == date:
                    item.pop('slack_number', None)
                    item.pop('slack_number_date', None)
            return result
        items, _ = await update_items(storage, set_numbers)
        # An item changed while numbers were being reserved: do not send a stale mapping.
        current = assign_todo_numbers(items, mapping)
        if current != mapping:
            raise PublishRejected('번호 예약 중 할 일이 바뀌었습니다. 발송을 다시 준비해 주세요.')
        areas = (await storage.read('areas'))['content']
        memos = {}
        visible = visible_ids(items, date)
        for item in items:
            if item['id'] in visible:
                try:
                    memo = (await storage.read('memos', doc=item['id']))['content']
                except StorageNotFound:
                    continue
                if memo:
                    memos[item['id']] = memo
        parts = render_daily_todo_messages(items, areas=areas, memos=memos, date=date,
                                           delivery_id=delivery_id, number_to_todo_id=mapping, todo_url=todo_url)
        for part in parts:
            response = slack_client.chat_postMessage(channel=channel, text=part.text, blocks=part.blocks)
            record = {'message_ts': response['ts'], 'numbers': part.numbers, 'snapshot': part.snapshot}
            sent.append(record)
            store.update(lambda state: state['deliveries'][delivery_id]['parts'].append(record))
        _verify_posted_parts(slack_client, channel, sent, parts, delivery_id)
        def succeed(state):
            d = state['deliveries'][delivery_id]
            d['status'] = 'success'
            d['sent_at'] = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
            old = state.get('active_delivery_id')
            if old and old in state['deliveries']:
                old_date = state['deliveries'][old]['date']
                state['days'][old_date]['active_delivery_id'] = None
            state['days'][date]['active_delivery_id'] = delivery_id
            state['active_delivery_id'] = delivery_id
            return dict(d)
        delivery = store.update(succeed)
        marked_success = True
        saved = store.read()
        if saved.get('active_delivery_id') != delivery_id or saved['deliveries'][delivery_id]['status'] != 'success':
            raise RuntimeError('발송 기록을 확인하지 못했습니다.')
    except Exception:
        def fail(state):
            d = state['deliveries'][delivery_id]
            if d['status'] != 'success':
                d['status'] = 'failed'
                d['error'] = '발송 또는 발송 확인에 실패했습니다.'
                d['parts'] = sent
        store.update(fail)
        if not marked_success:
            for part in sent:
                try:
                    messages = slack_client.conversations_replies(channel=channel, ts=part['message_ts'], limit=1).get('messages', [])
                    if messages:
                        _remove_old_daily_todo_actions(slack_client, channel, messages[0])
                except Exception:
                    logger.warning('발송에 실패한 TODO 메시지의 버튼을 제거하지 못했습니다.')
        raise

    session_mapping = _persist_message_sessions(session_manager, sent, channel_id=channel,
        user_id=recipient_user_id, username=role.get('username') or recipient_user_id,
        role=role['role'], target_session_id=target_session_id)
    cleanup_error = None
    try:
        # The old Atom message is discovered from the same DM, without reading Atom.
        history = _history(slack_client, channel, datetime.now(KST) - CLEANUP_LOOKBACK)
        old_ids = {d['delivery_id'] for d in store.read()['deliveries'].values()
                   if d.get('status') == 'success' and d['delivery_id'] != delivery_id}
        for message in history:
            if message.get('user') != EXPECTED_BOT_USER_ID:
                continue
            header = _header(message)
            if LEGACY_HEADER.fullmatch(header) or any(header.startswith(f'{HEADER_PREFIX}{old}:') for old in old_ids):
                _remove_old_daily_todo_actions(slack_client, channel, message)
    except Exception:
        cleanup_error = '이전 메시지의 버튼을 제거하지 못했습니다.'
    result = {**delivery, 'session_mapping': session_mapping}
    if cleanup_error:
        result['old_actions_cleanup_error'] = cleanup_error
    return result


def _verify_posted_parts(client, channel, records, expected_parts, delivery_id):
    for index, (record, expected) in enumerate(zip(records, expected_parts, strict=True), 1):
        messages = client.conversations_replies(channel=channel, ts=record['message_ts'], limit=1).get('messages', [])
        if not messages or messages[0].get('user') != EXPECTED_BOT_USER_ID:
            raise RuntimeError('발송한 TODO 메시지의 봇을 확인하지 못했습니다.')
        actual = messages[0].get('blocks', [])
        if not actual or actual[0].get('block_id') != f'{HEADER_PREFIX}{delivery_id}:{index}':
            raise RuntimeError('발송한 TODO 메시지 머리말을 확인하지 못했습니다.')
        def values(blocks):
            return [element.get('value') for block in blocks if block.get('type') == 'actions' for element in block.get('elements', [])]
        if len(actual) != len(expected.blocks) or values(actual) != values(expected.blocks):
            raise RuntimeError('발송한 TODO 메시지의 버튼을 확인하지 못했습니다.')


def _remove_old_daily_todo_actions(client, channel, message):
    filtered = []
    for block in message.get('blocks', []):
        if block.get('type') != 'actions':
            filtered.append(block)
            continue
        elements = [element for element in block.get('elements', [])
                    if element.get('action_id') != 'daily_todo_set_completion'
                    and not str(element.get('action_id', '')).startswith(ACTION_ID_PREFIX)]
        if elements:
            filtered.append({**block, 'elements': elements})
    if filtered != message.get('blocks', []):
        client.chat_update(channel=channel, ts=message['ts'], blocks=filtered)

def _persist_message_sessions(
    session_manager,
    parts: list[dict[str, Any]],
    *,
    channel_id: str,
    user_id: str,
    username: str,
    role: str,
    target_session_id: str,
) -> dict[str, Any]:
    from pathlib import Path

    from seosoyoung.slackbot.soulstream.session import SessionManager

    failures = []
    session_dir = getattr(session_manager, "session_dir", None)
    if session_dir is None:
        return {"status": "partial", "failures": [{"error": "session storage path is unavailable"}]}
    for part in parts:
        message_ts = part["message_ts"]
        try:
            created = session_manager.create(
                thread_ts=message_ts,
                channel_id=channel_id,
                user_id=user_id,
                username=username,
                role=role,
            )
            updated = session_manager.update_session_id(message_ts, target_session_id)
            if created is None or updated is None:
                raise RuntimeError("SessionManager did not return the saved thread mapping")
            persisted = SessionManager(session_dir=Path(session_dir)).get(message_ts)
            if (
                persisted is None
                or persisted.thread_ts != message_ts
                or persisted.channel_id != channel_id
                or persisted.user_id != user_id
                or persisted.username != username
                or persisted.session_id != target_session_id
                or persisted.role != role
            ):
                raise RuntimeError("persisted thread mapping failed readback")
        except Exception as exc:
            failures.append({"message_ts": message_ts, "error": f"{type(exc).__name__}: {exc}"})
            logger.exception("TODO message sent but SessionManager mapping was not verified")
    return {"status": "success" if not failures else "partial", "failures": failures}



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='일일 할 일을 Slack으로 발송하거나 준비 기록을 저장합니다.')
    sub = parser.add_subparsers(dest='command', required=True)
    publish = sub.add_parser('publish')
    publish.add_argument('--app-id', default='todo')
    publish.add_argument('--date', required=True)
    publish.add_argument('--recipient-user-id', required=True)
    publish.add_argument('--target-session-id', required=True)
    publish.add_argument('--force', action='store_true')
    publish.add_argument('--reason')
    prepare = sub.add_parser('prepare', help='표준입력 JSON을 날짜별 준비 기록으로 저장')
    prepare.add_argument('--date', required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    Date.fromisoformat(args.date)
    from seosoyoung.slackbot.config import Config
    store = DeliveryStore(Path(Config.get_session_path()) / 'daily_todo' / 'state.json')
    if args.command == 'prepare':
        record = json.load(sys.stdin)
        if not isinstance(record, dict):
            raise SystemExit('준비 기록은 JSON 객체여야 합니다.')
        store.update(lambda state: state['preparation'].__setitem__(args.date, record))
        print(json.dumps({'date': args.date, 'preparation': store.read()['preparation'][args.date]}, ensure_ascii=False))
        return 0
    if args.force and not (args.reason and args.reason.strip()):
        raise SystemExit('--force requires --reason')
    from slack_sdk import WebClient
    from seosoyoung.slackbot.auth import get_user_role
    from seosoyoung.slackbot.soulstream.session import SessionManager
    result = asyncio.run(publish_daily_todo(StorageClient(app_id=args.app_id), store,
        WebClient(token=Config.slack.bot_token), SessionManager(session_dir=Path(Config.get_session_path())),
        date=args.date, recipient_user_id=args.recipient_user_id, target_session_id=args.target_session_id,
        get_user_role=get_user_role, todo_url=os.environ.get('DAILY_TODO_APP_LINK') or None,
        force=args.force, reason=args.reason))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
