"""Daily TODO parser contracts for the hidden operations comment."""

import json

import pytest


@pytest.fixture
def long_daily_todo_card():
    """A redacted card-shaped fixture matching the current large metadata comment."""
    archive = [
        {
            "id": f"2026-08-{(index % 28) + 1:02d}:{index}",
            "record": (
                f"- ~~[완료 기록 {index}](https://example.test/{index})~~ "
                f"(10/26 완료 확인) <!-- 이전 주석 {index} -->"
            ),
            "hidden_from": "recent_window",
            "evidence": f"fixture-evidence-{index}",
            "actual_completed_date": None,
            "first_confirmed_date": "2026-10-26",
            "reason": "fixture",
            "completed_date": "2026-10-26",
            "memo": "원문 메모 보존",
        }
        for index in range(63)
    ]
    metadata = {
        "date": "2026-10-27",
        "timezone": "Asia/Seoul",
        "mode": "remind",
        "created_at": "2026-10-27T08:00:00+09:00",
        "prepared_at": "2026-10-27T07:00:00+09:00",
        "evidence_until": "2026-10-27T08:00:00+09:00",
        "reminder_date": "2026-10-27",
        "target_session_id": "fixture-session",
        "work_override": None,
        "holiday": {"status": "workday"},
        "carry_source": {"date": "2026-10-26", "card_id": "fixture-old-card"},
        "prior_work_overrides": [],
        "prior_delivery_history": [
            {"date": f"2026-10-{index + 1:02d}", "evidence": "기록 보존 " * 180}
            for index in range(6)
        ],
        "completed_archive": archive,
        "recent_window": {"dates": ["2026-10-26", "2026-10-27"]},
        "upcoming_window": {"dates": ["2026-10-28"]},
        "reconciliation": "기존 맥락 보존 " * 180,
        "evidence_sources": [{"name": "fixture", "evidence": "근거 " * 220}],
        "evidence_limits": "fixture-only",
        "upsert": "기존 항목만 갱신",
        "scope": "회사일·개인개발·개인사",
        "remind_changes": {"changes": []},
        "pas_identity": {"session_id": "fixture-session"},
        "delivery_attempt": {"status": "verified"},
        "delivery": {"result": "ok"},
        "delivery_channel": "slack_dm",
        "prior_slack_deliveries": [{"status": "sent", "format": "legacy"}],
        "slack_delivery": {
            "ok": True,
            "status": "verified",
            "message_readback_verified": True,
            "readback_evidence": "legacy-success",
        },
    }
    # The stored source escapes angle brackets so a past HTML comment cannot
    # terminate the outer operations comment before its JSON is parsed.
    serialized = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.replace("<", r"\u003c").replace(">", r"\u003e")
    return (
        "# 2026-10-27 TODO\n\n"
        "## 회사일\n"
        "- [ ] fixture task <!--todo:2026-10-27:1-->\n\n"
        f"<!-- daily-todo {serialized} -->"
    ), metadata


def test_large_real_shaped_metadata_round_trips_without_closing_comment(
    long_daily_todo_card,
):
    from seosoyoung.slackbot.daily_todo.parser import (
        parse_daily_todo_card,
        replace_daily_todo_metadata,
    )

    content, expected_metadata = long_daily_todo_card
    parsed = parse_daily_todo_card(content)
    rewritten = replace_daily_todo_metadata(
        content,
        {**parsed.metadata, "slack_todo_active_delivery_id": "fixture-delivery"},
    )
    reparsed = parse_daily_todo_card(rewritten)
    metadata_comment = rewritten[rewritten.index("<!-- daily-todo ") :]

    assert len(metadata_comment) > 20_000
    assert "완료 기록" in metadata_comment
    assert r"\u003c!-- 이전 주석" in metadata_comment
    assert r"--\u003e" in metadata_comment
    assert "-->" not in metadata_comment[: metadata_comment.rfind(" -->")]
    assert reparsed.metadata["completed_archive"] == expected_metadata["completed_archive"]
    assert reparsed.metadata["slack_todo_active_delivery_id"] == "fixture-delivery"
    assert reparsed.content_before_metadata == parsed.content_before_metadata


def test_todo_rows_keep_category_tree_and_stable_ids():
    from seosoyoung.slackbot.daily_todo.parser import parse_todo_items

    content = """# 2026-10-27 TODO

## 회사일
- 프로젝트 준비 <!--todo:2026-10-27:1-->
  - 외부 확인 대기 <!--todo:2026-10-27:2-->
  - ~~기존 완료~~ (10/26 완료 확인) <!--todo:2026-10-26:3-->
  - 보류 항목 (보류) <!--todo:2026-10-27:4-->
  - 설명만 있는 하위 내용

## 개인개발
- 개별 작업 <!--todo:2026-10-27:5-->

## 개인사
- 단순 설명은 번호 대상 아님
"""
    items = parse_todo_items(content)

    assert [(item.todo_id, item.category) for item in items] == [
        ("2026-10-27:1", "회사일"),
        ("2026-10-27:2", "회사일"),
        ("2026-10-26:3", "회사일"),
        ("2026-10-27:4", "회사일"),
        ("2026-10-27:5", "개인개발"),
    ]
    assert items[0].is_group is True
    assert items[1].is_group is False
    assert items[1].is_completed is False
    assert items[2].is_completed is True
    assert items[3].is_blocked is True
    assert items[1].text == "외부 확인 대기"


def test_number_display_is_parsed_and_kept_outside_completion_markup():
    from seosoyoung.slackbot.daily_todo.parser import (
        parse_todo_items,
        set_task_completion,
        set_task_number,
    )

    content = "## 회사일\n- 작업 — 메모 <!--todo:2026-10-27:8-->"
    numbered = set_task_number(content, "2026-10-27:8", 8)
    item = parse_todo_items(numbered)[0]
    completed = set_task_completion(
        numbered,
        "2026-10-27:8",
        completed=True,
        annotation="10/27 완료 확인",
    )
    reopened = set_task_completion(
        completed,
        "2026-10-27:8",
        completed=False,
        annotation="10/27 완료 확인",
    )

    assert numbered == "## 회사일\n- **8.** 작업 — 메모 <!--todo:2026-10-27:8-->"
    assert item.display_number == 8
    assert item.text == "작업 — 메모"
    assert "- **8.** ~~작업~~ — 메모 (10/27 완료 확인)" in completed
    assert "- **8.** 작업 — 메모" in reopened
    assert "~~8." not in completed


def test_completion_edit_changes_only_selected_task_name_and_annotation():
    from seosoyoung.slackbot.daily_todo.parser import set_task_completion

    content = "## 회사일\n- [차량 점검](https://example.test) — 사람 확인 대기 <!--todo:2026-10-27:7-->"

    completed = set_task_completion(
        content,
        "2026-10-27:7",
        completed=True,
        annotation="10/27 완료 확인, 실제 완료일 미상",
    )
    reopened = set_task_completion(
        completed,
        "2026-10-27:7",
        completed=False,
        annotation="10/27 완료 확인, 실제 완료일 미상",
    )

    assert "~~[차량 점검](https://example.test)~~" in completed
    assert "10/27 완료 확인, 실제 완료일 미상" in completed
    assert "사람 확인 대기" in completed
    assert "~~" not in reopened
    assert "10/27 완료 확인, 실제 완료일 미상" not in reopened
    assert "사람 확인 대기" in reopened
    assert "<!--todo:2026-10-27:7-->" in reopened
