import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from seosoyoung.slackbot.daily_todo.parser import parse_daily_todo_card
from seosoyoung.slackbot.daily_todo.publisher import PublishRejected, publish_daily_todo


def _card(metadata_extra=None):
    metadata = {"date": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()}
    metadata.update(metadata_extra or {})
    value = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    value = value.replace("<", r"\u003c").replace(">", r"\u003e")
    return {
        "id": "card-1",
        "version": 1,
        "content": (
            "# 오늘 TODO\n\n## 회사일\n"
            "- 프로젝트 묶음 <!--todo:2026-10-27:group-->\n"
            "  - 첫 작업 <!--todo:2026-10-27:1-->\n"
            "  - 둘째 작업 <!--todo:2026-10-27:2-->\n\n"
            f"<!-- daily-todo {value} -->"
        ),
    }


class FakeAtom:
    def __init__(self, metadata=None):
        self.card = _card(metadata)
        self.updates = []

    async def get_card(self, card_id):
        return dict(self.card)

    async def update_card(self, card_id, *, content, expected_version):
        assert expected_version == self.card["version"]
        self.updates.append(content)
        self.card = {**self.card, "version": expected_version + 1, "content": content}


class FakeSlack:
    def __init__(self):
        self.posts = []
        self.updates = []
        self.auth_calls = 0
        self.messages = {}

    def auth_test(self):
        self.auth_calls += 1
        return {"team_id": "team-1", "user_id": "bot-1"}

    def conversations_open(self, *, users):
        return {"channel": {"id": "channel-1"}}

    def users_info(self, *, user):
        return {"user": {"name": "recipient"}}

    def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        ts = f"123.{len(self.posts):03d}"
        self.messages[ts] = {"user": "bot-1", "ts": ts, "text": kwargs["text"], "blocks": kwargs["blocks"]}
        return {"ts": ts}

    def conversations_replies(self, *, channel, ts, limit):
        return {"messages": [self.messages[ts]] if ts in self.messages else []}

    def chat_update(self, *, channel, ts, text, blocks):
        self.updates.append(ts)
        self.messages[ts] = {**self.messages[ts], "text": text, "blocks": blocks}


class FakeSessions:
    def __init__(self):
        self.created = []
        self.updated = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return object()

    def update_session_id(self, thread_ts, session_id):
        self.updated.append((thread_ts, session_id))


@pytest.mark.asyncio
async def test_publish_persists_mapping_and_activates_only_after_messages_are_sent():
    atom, slack, sessions = FakeAtom(), FakeSlack(), FakeSessions()
    result = await publish_daily_todo(
        atom,
        slack,
        sessions,
        card_id="card-1",
        todo_node_id="node-1",
        recipient_user_id="user-1",
        target_session_id="session-1",
    )
    saved = parse_daily_todo_card(atom.card["content"]).metadata
    delivery = saved["slack_todo_deliveries"][-1]

    assert result["status"] == "success"
    assert saved["slack_todo_active_delivery_id"] == result["delivery_id"]
    assert delivery["status"] == "success"
    assert delivery["source_card_id"] == "card-1"
    assert set(delivery["number_to_todo_id"].values()) == {
        "2026-10-27:1",
        "2026-10-27:2",
    }
    assert delivery["parts"][0]["message_ts"] == "123.001"
    assert slack.posts[0]["blocks"][0]["block_id"].startswith(
        f"daily_todo_header:card-1:{result['delivery_id']}:"
    )
    assert sessions.updated == [("123.001", "session-1")]


@pytest.mark.asyncio
async def test_existing_legacy_success_requires_force_and_reason_before_sending():
    atom = FakeAtom({"slack_delivery": {"ok": True, "status": "verified"}})
    slack, sessions = FakeSlack(), FakeSessions()
    with pytest.raises(PublishRejected):
        await publish_daily_todo(
            atom,
            slack,
            sessions,
            card_id="card-1",
            todo_node_id="node-1",
            recipient_user_id="user-1",
            target_session_id="session-1",
        )
    assert slack.posts == []


@pytest.mark.asyncio
async def test_force_requires_reason():
    atom, slack, sessions = FakeAtom(), FakeSlack(), FakeSessions()
    with pytest.raises(PublishRejected, match="reason"):
        await publish_daily_todo(
            atom,
            slack,
            sessions,
            card_id="card-1",
            todo_node_id="node-1",
            recipient_user_id="user-1",
            target_session_id="session-1",
            force=True,
        )


@pytest.mark.asyncio
async def test_forced_resend_keeps_old_mapping_and_removes_only_old_todo_actions():
    old_delivery = {
        "delivery_id": "old-delivery",
        "source_card_id": "card-1",
        "date": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        "team_id": "team-1",
        "bot_user_id": "bot-1",
        "recipient_user_id": "user-1",
        "channel_id": "channel-1",
        "status": "success",
        "number_to_todo_id": {"1": "2026-10-27:1", "2": "2026-10-27:2"},
        "parts": [{"message_ts": "old.001", "numbers": [1, 2]}],
    }
    atom = FakeAtom(
        {
            "slack_todo_active_delivery_id": "old-delivery",
            "slack_todo_deliveries": [old_delivery],
        }
    )
    slack, sessions = FakeSlack(), FakeSessions()
    slack.messages["old.001"] = {
        "user": "bot-1",
        "ts": "old.001",
        "text": "old TODO",
        "blocks": [
            {"type": "section", "block_id": "daily_todo_header:card-1:old-delivery:1", "text": {"type": "mrkdwn", "text": "TODO"}},
            {
                "type": "actions",
                "elements": [
                    {"action_id": "daily_todo_set_completion", "value": "old"},
                    {"action_id": "other_action", "value": "keep"},
                ],
            },
        ],
    }

    result = await publish_daily_todo(
        atom,
        slack,
        sessions,
        card_id="card-1",
        todo_node_id="node-1",
        recipient_user_id="user-1",
        target_session_id="session-1",
        force=True,
        reason="recipient asked for a resend",
    )
    metadata = parse_daily_todo_card(atom.card["content"]).metadata
    old_blocks = slack.messages["old.001"]["blocks"]

    assert metadata["slack_todo_active_delivery_id"] == result["delivery_id"]
    assert metadata["slack_todo_deliveries"][0]["number_to_todo_id"] == old_delivery["number_to_todo_id"]
    assert metadata["slack_todo_deliveries"][-1]["reason"] == "recipient asked for a resend"
    assert old_blocks[0]["block_id"] == "daily_todo_header:card-1:old-delivery:1"
    assert len(old_blocks) == 2
    assert old_blocks[-1]["elements"][0]["action_id"] == "other_action"
