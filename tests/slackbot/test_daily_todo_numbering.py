from seosoyoung.slackbot.daily_todo.numbering import (
    assign_todo_numbers,
    read_delivery_number_map,
)
from seosoyoung.slackbot.daily_todo.parser import parse_todo_items


def test_new_numbers_skip_group_completed_and_held_rows_and_append_globally():
    content = """# 2026-10-27 TODO
## 회사일
- 목표 묶음 <!--todo:2026-10-27:1-->
  - 첫 할 일 <!--todo:2026-10-27:2-->
  - ~~지난 완료~~ (10/26 완료 확인) <!--todo:2026-10-26:3-->
  - 보류 (보류) <!--todo:2026-10-27:4-->
## 개인개발
- 새 작업 <!--todo:2026-10-27:5-->
"""
    items = parse_todo_items(content)

    new_day_numbers = assign_todo_numbers(items, {})
    assert new_day_numbers == {
        1: "2026-10-27:2",
        2: "2026-10-27:5",
    }

    continued = assign_todo_numbers(
        items,
        {
            3: "2026-10-26:3",
            8: "2026-10-27:2",
            9: "2026-10-26:99",
        },
    )
    assert continued == {
        8: "2026-10-27:2",
        10: "2026-10-27:5",
    }


def test_delivery_number_history_is_scoped_to_day_and_source_card():
    metadata = {
        "slack_todo_deliveries": [
            {
                "delivery_id": "old-day",
                "date": "2026-10-26",
                "source_card_id": "card-a",
                "number_to_todo_id": {"1": "old"},
            },
            {
                "delivery_id": "other-card",
                "date": "2026-10-27",
                "source_card_id": "card-b",
                "number_to_todo_id": {"1": "other"},
            },
            {
                "delivery_id": "same-day",
                "date": "2026-10-27",
                "source_card_id": "card-a",
                "number_to_todo_id": {"1": "kept", "3": "removed"},
            },
        ]
    }

    assert read_delivery_number_map(
        metadata, date="2026-10-27", source_card_id="card-a"
    ) == {1: "kept", 3: "removed"}


def test_new_delivery_keeps_only_current_eligible_items_and_appends_after_all_history():
    content = """## 회사일
- **1.** ~~완료한 작업~~ (10/27 완료 확인) <!--todo:completed-->
- **2.** 진행 중인 작업 <!--todo:active-->
- **3.** 취소한 작업 (취소) <!--todo:cancelled-->
- **4.** 작업 묶음 <!--todo:group-->
  - **6.** ~~완료된 하위 작업~~ (완료 확인) <!--todo:completed-child-->
- **5.** 보류한 작업 (보류) <!--todo:blocked-->
- 새 작업 <!--todo:new-->
"""
    prior = {
        1: "completed",
        2: "active",
        3: "cancelled",
        4: "group",
        5: "blocked",
        6: "completed-child",
        91: "deleted",
    }

    assert assign_todo_numbers(parse_todo_items(content), prior) == {
        2: "active",
        92: "new",
    }
