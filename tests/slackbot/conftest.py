from copy import deepcopy

import pytest

from seosoyoung.slackbot.daily_todo.storage_client import StorageConflict, StorageNotFound
from seosoyoung.slackbot.daily_todo.publisher import EXPECTED_TEAM_ID, EXPECTED_BOT_USER_ID, EXPECTED_BOT_ID, EXPECTED_RECIPIENT_USER_ID


class FakeStorage:
    app_id = 'todo'
    url = 'https://example.test/mcp'

    def __init__(self, items=None):
        self.items = deepcopy(items or [])
        self.revision = 1
        self.conflicts = 0
        self.writes = []
        self.memos = {}

    async def read(self, entry_id, *, doc=None):
        if entry_id == 'items':
            return {'content': deepcopy(self.items), 'revision': str(self.revision)}
        if entry_id == 'areas':
            return {'content': ['회사일', '개인개발', '개인사'], 'revision': None}
        if doc not in self.memos:
            raise StorageNotFound('메모가 없습니다.')
        return {'content': self.memos[doc], 'revision': None}

    async def write(self, entry_id, content, revision, *, doc=None):
        self.writes.append((entry_id, deepcopy(content), revision, doc))
        if self.conflicts:
            self.conflicts -= 1
            self.revision += 1
            self.items[0]['concurrent'] = self.revision
            raise StorageConflict('conflict')
        assert revision == str(self.revision)
        self.items = deepcopy(content)
        self.revision += 1
        return {'revision': str(self.revision)}


class FakeSlack:
    def __init__(self):
        self.messages = []
        self.updates = []
        self.fail_post_at = None
        self.post_count = 0
        self.history_calls = []

    def auth_test(self):
        return {'team_id': EXPECTED_TEAM_ID, 'user_id': EXPECTED_BOT_USER_ID, 'bot_id': EXPECTED_BOT_ID}

    def conversations_open(self, **kwargs):
        return {'channel': {'id': 'dm'}}

    def chat_postMessage(self, **kwargs):
        self.post_count += 1
        if self.post_count == self.fail_post_at:
            raise RuntimeError('post failed')
        message = {**deepcopy(kwargs), 'ts': str(self.post_count), 'user': EXPECTED_BOT_USER_ID}
        self.messages.append(message)
        return {'ts': message['ts']}

    def conversations_replies(self, *, channel, ts, limit):
        return {'messages': [deepcopy(m) for m in self.messages if m['ts'] == ts]}

    def conversations_history(self, **kwargs):
        self.history_calls.append(deepcopy(kwargs))
        return {'messages': deepcopy(self.messages), 'response_metadata': {}}

    def chat_update(self, **kwargs):
        self.updates.append(deepcopy(kwargs))
        for message in self.messages:
            if message['ts'] == kwargs['ts']:
                message.update(deepcopy(kwargs))

    def reactions_add(self, **kwargs):
        pass


def role(user, client):
    return {'user_id': user, 'is_bot': False, 'role': 'admin', 'username': 'director'}


@pytest.fixture
def fake_storage():
    return FakeStorage([{'id': 'a', 'title': '첫 항목', 'area': '회사일', 'parent': None,
                         'status': 'open', 'done_on': None, 'order': 0}])


@pytest.fixture
def fake_slack():
    return FakeSlack()
