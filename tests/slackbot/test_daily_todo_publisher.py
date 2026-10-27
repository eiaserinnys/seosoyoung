import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from unittest.mock import MagicMock, patch

from seosoyoung.slackbot.daily_todo.parser import parse_daily_todo_card
from seosoyoung.slackbot.daily_todo.completion import set_completion
from seosoyoung.slackbot.daily_todo.publisher import (
    EXPECTED_BOT_ID,
    EXPECTED_BOT_USER_ID,
    EXPECTED_RECIPIENT_USER_ID,
    EXPECTED_TEAM_ID,
    PublishRejected,
    publish_daily_todo,
)
from seosoyoung.slackbot.soulstream.session import SessionManager


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
        self.cards = {self.card["id"]: self.card}
        self.updates = []
        self.reads = []

    async def get_card(self, card_id):
        self.reads.append(card_id)
        return dict(self.cards[card_id])

    async def update_card(self, card_id, *, content, expected_version):
        current = self.cards[card_id]
        assert expected_version == current["version"]
        self.updates.append(content)
        updated = {**current, "version": expected_version + 1, "content": content}
        self.cards[card_id] = updated
        if card_id == "card-1":
            self.card = updated


class FakeSlack:
    def __init__(self, *, auth=None, user=None):
        self.posts = []
        self.updates = []
        self.auth_calls = 0
        self.messages = {}
        self.auth = {
            "team_id": EXPECTED_TEAM_ID,
            "user_id": EXPECTED_BOT_USER_ID,
            "bot_id": EXPECTED_BOT_ID,
            **(auth or {}),
        }
        self.user = {
            "id": EXPECTED_RECIPIENT_USER_ID,
            "name": "recipient",
            "is_bot": False,
            **(user or {}),
        }
        self.open_calls = 0
        self.user_info_calls = 0

    def auth_test(self):
        self.auth_calls += 1
        return self.auth

    def conversations_open(self, *, users):
        self.open_calls += 1
        return {"channel": {"id": "channel-1"}}

    def users_info(self, *, user):
        self.user_info_calls += 1
        return {"user": self.user}

    def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        ts = f"123.{len(self.posts):03d}"
        self.messages[ts] = {
            "user": self.auth["user_id"],
            "ts": ts,
            "text": kwargs["text"],
            "blocks": kwargs["blocks"],
        }
        return {"ts": ts}

    def conversations_replies(self, *, channel, ts, limit):
        return {"messages": [self.messages[ts]] if ts in self.messages else []}

    def chat_update(self, *, channel, ts, text, blocks):
        self.updates.append(ts)
        self.messages[ts] = {**self.messages[ts], "text": text, "blocks": blocks}


class FakeSessions:
    def __init__(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.session_dir = Path(self._temporary_directory.name)
        self.manager = SessionManager(session_dir=self.session_dir)
        self.created = []
        self.updated = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        return self.manager.create(**kwargs)

    def update_session_id(self, thread_ts, session_id):
        self.updated.append((thread_ts, session_id))
        return self.manager.update_session_id(thread_ts, session_id)


def _get_user_role(user_id, client):
    user = client.users_info(user=user_id)["user"]
    return {
        "user_id": user.get("id", user_id),
        "username": user.get("name", user_id),
        "role": "viewer",
        "is_bot": user.get("is_bot", False),
    }


@patch("seosoyoung.slackbot.auth.Config")
def test_get_user_role_reports_the_users_info_identity(mock_config):
    from seosoyoung.slackbot.auth import get_user_role

    mock_config.auth.admin_users = set()
    mock_config.auth.role_tools = {"admin": [], "viewer": []}
    client = MagicMock()
    client.users_info.return_value = {
        "user": {"id": EXPECTED_RECIPIENT_USER_ID, "name": "director", "is_bot": False}
    }

    role = get_user_role("requested-user", client)

    assert role["user_id"] == EXPECTED_RECIPIENT_USER_ID
    assert role["role"] == "viewer"


@pytest.mark.asyncio
async def test_publish_persists_mapping_and_activates_only_after_messages_are_sent():
    atom, slack, sessions = FakeAtom(), FakeSlack(), FakeSessions()
    result = await publish_daily_todo(
        atom,
        slack,
        sessions,
        card_id="card-1",
        todo_node_id="node-1",
        recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
        target_session_id="session-1",
        get_user_role=_get_user_role,
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
    assert "- **1.** 첫 작업" in atom.card["content"]
    assert "- **2.** 둘째 작업" in atom.card["content"]
    assert result["session_mapping"]["status"] == "success"
    persisted = SessionManager(session_dir=sessions.session_dir).get("123.001")
    assert persisted is not None
    assert (persisted.channel_id, persisted.user_id, persisted.session_id, persisted.role) == (
        "channel-1",
        EXPECTED_RECIPIENT_USER_ID,
        "session-1",
        "viewer",
    )
    assert sessions.updated == [("123.001", "session-1")]


@pytest.mark.asyncio
async def test_session_link_failure_is_reported_without_turning_sent_delivery_into_failure(tmp_path):
    class MissingSaveSessions:
        session_dir = tmp_path

        def create(self, **kwargs):
            return object()

        def update_session_id(self, thread_ts, session_id):
            return object()

    atom, slack = FakeAtom(), FakeSlack()
    result = await publish_daily_todo(
        atom,
        slack,
        MissingSaveSessions(),
        card_id="card-1",
        todo_node_id="node-1",
        recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
        target_session_id="session-1",
        get_user_role=_get_user_role,
    )

    assert result["status"] == "success"
    assert result["session_mapping"]["status"] == "partial"
    assert result["session_mapping"]["failures"][0]["message_ts"] == "123.001"
    assert len(slack.posts) == 1
    assert parse_daily_todo_card(atom.card["content"]).metadata[
        "slack_todo_active_delivery_id"
    ] == result["delivery_id"]
    assert slack.posts[0]["blocks"][0]["block_id"].startswith(
        f"daily_todo_header:card-1:{result['delivery_id']}:"
    )


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
            recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
            target_session_id="session-1",
            get_user_role=_get_user_role,
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
            recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
            target_session_id="session-1",
            get_user_role=_get_user_role,
            force=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("auth", "user", "recipient"),
    [
        ({"team_id": "wrong-team"}, None, EXPECTED_RECIPIENT_USER_ID),
        ({"user_id": "wrong-bot-user"}, None, EXPECTED_RECIPIENT_USER_ID),
        ({"bot_id": "wrong-bot"}, None, EXPECTED_RECIPIENT_USER_ID),
        ({}, {"id": "wrong-user"}, EXPECTED_RECIPIENT_USER_ID),
        ({}, None, "U000OTHER"),
    ],
)
async def test_wrong_slack_identity_is_rejected_before_atom_write_or_message_send(auth, user, recipient):
    atom = FakeAtom()
    slack = FakeSlack(auth=auth, user=user)

    with pytest.raises(PublishRejected):
        await publish_daily_todo(
            atom,
            slack,
            FakeSessions(),
            card_id="card-1",
            todo_node_id="node-1",
            recipient_user_id=recipient,
            target_session_id="session-1",
            get_user_role=_get_user_role,
        )

    assert atom.reads == []
    assert atom.updates == []
    assert slack.posts == []
    assert slack.open_calls == 0


@pytest.mark.asyncio
async def test_forced_resend_keeps_old_mapping_and_removes_only_old_todo_actions():
    old_delivery = {
        "delivery_id": "old-delivery",
        "source_card_id": "card-1",
        "date": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        "team_id": EXPECTED_TEAM_ID,
        "bot_user_id": EXPECTED_BOT_USER_ID,
        "recipient_user_id": EXPECTED_RECIPIENT_USER_ID,
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
        "user": EXPECTED_BOT_USER_ID,
        "ts": "old.001",
        "text": "old TODO",
        "blocks": [
            {"type": "section", "block_id": "daily_todo_header:card-1:old-delivery:1", "text": {"type": "mrkdwn", "text": "TODO"}},
            {
                "type": "actions",
                "elements": [
                    {"action_id": "daily_todo_set_completion:1", "value": "old"},
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
        recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
        target_session_id="session-1",
        get_user_role=_get_user_role,
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


@pytest.mark.asyncio
async def test_new_day_deactivates_carry_source_buttons_but_keeps_old_number_reply_mapping():
    yesterday = (
        datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)
    ).isoformat()
    carry_source_id = "41e8a67e-3858-42af-beb7-9fa91aca6b67"
    old_delivery = {
        "delivery_id": "yesterday-delivery",
        "source_card_id": carry_source_id,
        "date": yesterday,
        "team_id": EXPECTED_TEAM_ID,
        "bot_user_id": EXPECTED_BOT_USER_ID,
        "recipient_user_id": EXPECTED_RECIPIENT_USER_ID,
        "channel_id": "channel-1",
        "status": "success",
        "number_to_todo_id": {"6": f"{yesterday}:6"},
        "parts": [{"message_ts": "old.006", "numbers": [6]}],
    }
    old_metadata = {
        "date": yesterday,
        "slack_todo_active_delivery_id": "yesterday-delivery",
        "slack_todo_deliveries": [old_delivery],
    }
    old_json = json.dumps(old_metadata, ensure_ascii=False, separators=(",", ":"))
    old_card = {
        "id": carry_source_id,
        "version": 9,
        "content": (
            f"## 회사일\n- **6.** 이전 작업 <!--todo:{yesterday}:6-->\n"
            f"<!-- daily-todo {old_json} -->"
        ),
    }
    atom = FakeAtom({"carry_source": {"date": yesterday, "card_id": carry_source_id}})
    atom.cards[carry_source_id] = old_card
    slack, sessions = FakeSlack(), FakeSessions()
    slack.messages["old.006"] = {
        "user": EXPECTED_BOT_USER_ID,
        "ts": "old.006",
        "text": "old TODO",
        "blocks": [
            {
                "type": "section",
                "block_id": f"daily_todo_header:{carry_source_id}:yesterday-delivery:1",
                "text": {"type": "mrkdwn", "text": "TODO"},
            },
            {
                "type": "actions",
                "elements": [
                    {"action_id": "daily_todo_set_completion:6", "value": "old"},
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
        recipient_user_id=EXPECTED_RECIPIENT_USER_ID,
        target_session_id="session-1",
        get_user_role=_get_user_role,
    )

    prior_metadata = parse_daily_todo_card(atom.cards[carry_source_id]["content"]).metadata
    assert "slack_todo_active_delivery_id" not in prior_metadata
    assert prior_metadata["slack_todo_deliveries"][0]["status"] == "success"
    assert prior_metadata["slack_todo_deliveries"][0]["number_to_todo_id"] == {"6": f"{yesterday}:6"}
    assert slack.messages["old.006"]["blocks"][0]["block_id"].startswith("daily_todo_header:")
    assert slack.messages["old.006"]["blocks"][1]["elements"][0]["action_id"] == "other_action"
    assert result["status"] == "success"
    assert "old_actions_cleanup_error" not in result

    outcome = await set_completion(
        atom,
        source_card_id=carry_source_id,
        delivery_id="yesterday-delivery",
        message_ts="old.006",
        part_index=1,
        numbers=[6],
        target_state="complete",
        actual_slack_user=EXPECTED_RECIPIENT_USER_ID,
        actual_team_id=EXPECTED_TEAM_ID,
        actual_channel_id="channel-1",
        actual_bot_user_id=EXPECTED_BOT_USER_ID,
        confirmed_at=datetime.now(timezone.utc).isoformat(),
    )
    assert outcome.changed
    assert "**6.** ~~이전 작업~~" in atom.cards[carry_source_id]["content"]
