import json

import pytest

from seosoyoung.slackbot.daily_todo.completion import (
    CompletionRejected,
    set_completion,
)


def _card():
    metadata = {
        "date": "2026-10-27",
        "slack_todo_active_delivery_id": "delivery-1",
        "slack_todo_deliveries": [
            {
                "delivery_id": "delivery-1",
                "source_card_id": "card-1",
                "date": "2026-10-27",
                "team_id": "team-1",
                "bot_user_id": "bot-1",
                "recipient_user_id": "user-1",
                "channel_id": "channel-1",
                "status": "success",
                "number_to_todo_id": {"1": "2026-10-27:1", "2": "2026-10-27:2"},
                "parts": [{"message_ts": "123.456", "numbers": [1, 2]}],
            }
        ],
    }
    raw = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("<", r"\u003c").replace(">", r"\u003e")
    return {
        "id": "card-1",
        "version": 4,
        "content": (
            "# 2026-10-27 TODO\n\n## 회사일\n"
            "- 부모 묶음 <!--todo:2026-10-27:parent-->\n"
            "  - 첫 작업 — 메모 <!--todo:2026-10-27:1-->\n"
            "  - 둘째 작업 <!--todo:2026-10-27:2-->\n\n"
            f"<!-- daily-todo {raw} -->"
        ),
    }


class FakeAtom:
    def __init__(self):
        self.card = _card()
        self.updates = []
        self.conflict_once = False

    async def get_card(self, card_id):
        return dict(self.card)

    async def update_card(self, card_id, *, content, expected_version):
        self.updates.append((card_id, expected_version, content))
        if self.conflict_once:
            self.conflict_once = False
            self.card = {**self.card, "version": self.card["version"] + 1}
            raise RuntimeError("VersionConflict: expected_version mismatch")
        assert expected_version == self.card["version"]
        self.card = {**self.card, "version": self.card["version"] + 1, "content": content}


@pytest.mark.asyncio
async def test_selection_changes_only_explicit_child_and_is_idempotent_on_repeat():
    atom = FakeAtom()
    args = dict(
        source_card_id="card-1",
        delivery_id="delivery-1",
        message_ts="123.456",
        part_index=1,
        numbers=[1],
        target_state="complete",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-26T15:30:00+00:00",
    )

    first = await set_completion(atom, **args)
    second = await set_completion(atom, **args)

    assert first.changed is True
    assert second.changed is False
    assert len(atom.updates) == 1
    assert "- 부모 묶음 <!--todo:2026-10-27:parent-->" in atom.card["content"]
    assert "~~첫 작업~~ — 메모 (10/27 완료 확인)" in atom.card["content"]
    assert "  - 둘째 작업 <!--todo:2026-10-27:2-->" in atom.card["content"]


@pytest.mark.asyncio
async def test_reopen_keeps_completion_event_and_removes_only_completion_marker():
    atom = FakeAtom()
    await set_completion(
        atom,
        source_card_id="card-1",
        delivery_id="delivery-1",
        message_ts="123.456",
        part_index=1,
        numbers=[1],
        target_state="complete",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-26T15:30:00+00:00",
    )
    reopened = await set_completion(
        atom,
        source_card_id="card-1",
        delivery_id="delivery-1",
        message_ts="123.456",
        part_index=1,
        numbers=[1],
        target_state="reopen",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-27T01:00:00+00:00",
    )
    assert reopened.changed
    assert "~~첫 작업~~" not in atom.card["content"]
    assert "(10/27 완료 확인)" not in atom.card["content"]
    assert "— 메모" in atom.card["content"]
    assert atom.card["content"].count('"state":"complete"') == 1
    assert atom.card["content"].count('"state":"reopen"') == 1


@pytest.mark.asyncio
async def test_rejects_entire_selection_before_any_update_when_identity_or_number_is_wrong():
    atom = FakeAtom()
    base = dict(
        source_card_id="card-1",
        delivery_id="delivery-1",
        message_ts="123.456",
        part_index=1,
        numbers=[1, 99],
        target_state="complete",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-26T15:30:00+00:00",
    )
    with pytest.raises(CompletionRejected):
        await set_completion(atom, **base)
    with pytest.raises(CompletionRejected):
        await set_completion(atom, **{**base, "actual_slack_user": "other-user", "numbers": [1]})
    with pytest.raises(CompletionRejected):
        await set_completion(atom, **{**base, "part_index": 2, "numbers": [1]})
    assert atom.updates == []


@pytest.mark.asyncio
async def test_retries_one_cas_conflict_against_the_fresh_card():
    atom = FakeAtom()
    atom.conflict_once = True
    outcome = await set_completion(
        atom,
        source_card_id="card-1",
        delivery_id="delivery-1",
        message_ts="123.456",
        part_index=1,
        numbers=[2],
        target_state="complete",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-26T15:30:00+00:00",
    )
    assert outcome.changed
    assert [version for _, version, _ in atom.updates] == [4, 5]
    assert atom.card["content"].count('"todo_id":"2026-10-27:2"') == 1


@pytest.mark.asyncio
async def test_old_delivery_updates_only_matching_id_carried_into_today_card():
    def card(card_id, date, deliveries, active, row):
        metadata = {
            "date": date,
            "slack_todo_active_delivery_id": active,
            "slack_todo_deliveries": deliveries,
        }
        raw = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        raw = raw.replace("<", r"\u003c").replace(">", r"\u003e")
        return {
            "id": card_id,
            "version": 1,
            "content": f"# TODO\n\n## 회사일\n- {row}\n\n<!-- daily-todo {raw} -->",
        }

    old_delivery = {
        "delivery_id": "old-delivery",
        "source_card_id": "old-card",
        "date": "2026-10-26",
        "team_id": "team-1",
        "bot_user_id": "bot-1",
        "recipient_user_id": "user-1",
        "channel_id": "channel-1",
        "status": "success",
        "number_to_todo_id": {"1": "2026-10-26:7"},
        "parts": [{"message_ts": "old.123", "numbers": [1]}],
    }
    current_delivery = {
        "delivery_id": "today-delivery",
        "source_card_id": "today-card",
        "date": "2026-10-27",
        "team_id": "team-1",
        "bot_user_id": "bot-1",
        "recipient_user_id": "user-1",
        "channel_id": "channel-1",
        "status": "success",
        "todo_url": "https://atom.example.test/#today",
        "number_to_todo_id": {"8": "2026-10-26:7"},
        "parts": [{"message_ts": "today.123", "numbers": [8]}],
    }
    old = card(
        "old-card",
        "2026-10-26",
        [old_delivery],
        "old-delivery",
        "작업 <!--todo:2026-10-26:7-->",
    )
    today = card(
        "today-card",
        "2026-10-27",
        [current_delivery],
        "today-delivery",
        "이월 작업 <!--todo:2026-10-26:7-->",
    )

    class CarryAtom:
        def __init__(self):
            self.cards = {"old-card": old, "today-card": today}

        async def get_card(self, card_id):
            return dict(self.cards[card_id])

        async def update_card(self, card_id, *, content, expected_version):
            current = self.cards[card_id]
            assert current["version"] == expected_version
            self.cards[card_id] = {**current, "version": expected_version + 1, "content": content}

        async def search_cards(self, query, *, limit=10):
            assert query == '"2026-10-26:7"'
            return [{"id": "today-card"}]

    atom = CarryAtom()
    outcome = await set_completion(
        atom,
        source_card_id="old-card",
        delivery_id="old-delivery",
        message_ts="old.123",
        part_index=1,
        numbers=[1],
        target_state="complete",
        actual_slack_user="user-1",
        actual_team_id="team-1",
        actual_channel_id="channel-1",
        actual_bot_user_id="bot-1",
        confirmed_at="2026-10-26T15:30:00+00:00",
    )

    assert "~~작업~~" in atom.cards["old-card"]["content"]
    assert "~~이월 작업~~" in atom.cards["today-card"]["content"]
    assert len(outcome.current_refreshes) == 1
    assert outcome.current_refreshes[0]["delivery"]["delivery_id"] == "today-delivery"
    assert outcome.partial_error is None
