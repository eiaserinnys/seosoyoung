import json

import pytest

from seosoyoung.slackbot.daily_todo.numbering import assign_todo_numbers
from seosoyoung.slackbot.daily_todo.parser import parse_todo_items
from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages


def _numbered_content(open_count: int) -> str:
    lines = [
        "# 2026-10-27 TODO",
        "",
        "## 회사일",
        "- 프로젝트 묶음 <!--todo:2026-10-27:group-->",
    ]
    lines.extend(
        f"  - 회사 작업 {index} <!--todo:2026-10-27:{index}-->"
        for index in range(1, open_count + 1)
    )
    lines.extend(
        [
            "- 명시 취소 (취소) <!--todo:2026-10-27:cancelled-->",
            "",
            "## 개인개발",
            "- ~~이전 완료~~ (10/26 완료 확인) <!--todo:2026-10-26:99-->",
            "- 개발 설명만 있는 문맥",
            "",
            "## 개인사",
            "- 개인 항목",
        ]
    )
    return "\n".join(lines)


def test_preamble_deduplicates_only_today_date_and_todo_link():
    todo_url = "https://atom.example.test/#today-node"
    content = "\n".join(
        [
            f"2026-10-27 [오늘 TODO]({todo_url}) [안내](https://example.test/guide)",
            "## 회사일",
            "- 2026-10-27 [작업 링크](https://example.test/work) <!--todo:work-->",
        ]
    )
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-1",
        number_to_todo_id={1: "work"},
        todo_url=todo_url,
    )[0]

    assert part.text.count(todo_url) == 1
    assert part.text.count("10/27 확인") == 1
    assert part.text.count("오늘 추가하거나 바꿀 일이 있으신가요?") == 1
    assert part.text.count("2026-10-27") == 1
    assert "https://example.test/guide" in part.text
    assert "https://example.test/work" in part.text


def test_long_fallback_is_shortened_without_changing_blocks_or_completion_mapping():
    date = "2026-10-27"
    todo_url = "https://atom.example.test/#today-node"
    content = "\n".join(
        [
            f"# {date} TODO",
            "## 회사일",
            *(
                f"- 회사 작업 {number} "
                + "상세 설명 " * 70
                + f"<!--todo:{date}:{number}-->"
                for number in range(1, 12)
            ),
            "## 개인개발",
            "- ~~완료 작업~~ (10/26 완료 확인) <!--todo:2026-10-26:99-->",
            "## 개인사",
            "- 개인 일정",
        ]
    )
    mapping = {
        **{number: f"{date}:{number}" for number in range(1, 12)},
        12: "2026-10-26:99",
    }

    part = render_daily_todo_messages(
        content,
        metadata={"date": date},
        source_card_id="source-card",
        delivery_id="delivery-long",
        number_to_todo_id=mapping,
        todo_url=todo_url,
    )[0]

    blocks_text = "\n".join(
        block["text"]["text"] for block in part.blocks if block["type"] == "section"
    )
    buttons = [
        button
        for block in part.blocks
        if block["type"] == "actions"
        for button in block["elements"]
    ]
    payloads = [json.loads(button["value"]) for button in buttons]

    assert len(blocks_text) > 4000
    assert len(part.text) <= 4000
    assert part.text != blocks_text
    assert "10/27 확인" in part.text
    assert todo_url in part.text
    assert "회사일" in part.text
    assert "개인개발" in part.text
    assert "개인사" in part.text
    assert "오늘 추가하거나 바꿀 일이 있으신가요?" in part.text
    assert [payload["number"] for payload in payloads] == list(range(1, 13))
    assert [button["action_id"] for button in buttons] == [
        f"daily_todo_set_completion:{number}" for number in range(1, 13)
    ]
    assert buttons[-1]["text"]["text"] == "↺12"
    assert payloads[-1]["target_state"] == "reopen"
    assert "상세 설명" in blocks_text


def test_fallback_text_under_4000_characters_is_unchanged():
    todo_url = "https://atom.example.test/#today-node"
    part = render_daily_todo_messages(
        "## 회사일\n- 짧은 작업 <!--todo:2026-10-27:1-->",
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-short",
        number_to_todo_id={1: "2026-10-27:1"},
        todo_url=todo_url,
    )[0]
    original_text = "\n".join(
        block["text"]["text"] for block in part.blocks if block["type"] == "section"
    )

    assert len(original_text) <= 4000
    assert part.text == original_text


def test_actions_follow_at_most_ten_work_rows_and_keep_tree_context():
    content = _numbered_content(11)
    mapping = {
        12: "2026-10-26:99",
        **{13 + index: f"2026-10-27:{index + 1}" for index in range(11)},
    }
    from seosoyoung.slackbot.daily_todo.parser import set_task_number

    for number, todo_id in mapping.items():
        content = set_task_number(content, todo_id, number)
    parts = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-123",
        number_to_todo_id=mapping,
        todo_url="https://atom.example.test/#today-node",
    )

    assert len(parts) == 1
    blocks = parts[0].blocks
    assert blocks[0]["block_id"].startswith("daily_todo_header:source-card:delivery-123:")
    assert len(blocks) < 50
    assert all(
        len(block["text"]["text"]) <= 3000
        for block in blocks
        if block["type"] == "section" and block.get("text", {}).get("type") == "mrkdwn"
    )
    assert [
        len(block["elements"])
        for block in blocks
        if block["type"] == "actions"
    ] == [10, 1, 1]
    assert all(block["type"] == "actions" for block in blocks if block["type"] == "actions")
    assert "프로젝트 묶음" in "\n".join(
        block.get("text", {}).get("text", "") for block in blocks
    )
    assert "*12.*" in "\n".join(
        block.get("text", {}).get("text", "") for block in blocks
    )
    assert "취소" in "\n".join(
        block.get("text", {}).get("text", "") for block in blocks
    )

    buttons = [
        button
        for block in blocks
        if block["type"] == "actions"
        for button in block["elements"]
    ]
    payloads = [json.loads(button["value"]) for button in buttons]
    action_ids = [button["action_id"] for button in buttons]
    assert len(action_ids) == len(set(action_ids))
    assert action_ids == [f"daily_todo_set_completion:{number}" for number in list(range(13, 24)) + [12]]
    assert [payload["number"] for payload in payloads] == list(range(13, 24)) + [12]
    assert payloads[-1]["target_state"] == "reopen"
    assert buttons[-1]["text"]["text"] == "↺12"
    assert buttons[0]["accessibility_label"].startswith("13번 회사 작업 1")
    assert parts[0].numbers == list(range(13, 24)) + [12]
    fallback = parts[0].text
    assert fallback.count("오늘 추가하거나 바꿀 일이 있으신가요?") == 1
    assert fallback.count("https://atom.example.test/#today-node") == 1


def test_first_publish_moves_only_standalone_completed_rows_after_categories():
    content = "\n".join(
        [
            "# 2026-10-27 TODO",
            "## 회사일",
            "- 회사 작업 <!--todo:2026-10-27:1-->",
            "- 묶음 작업 <!--todo:2026-10-27:group-->",
            "  - ~~연관 완료~~ (10/26 완료 확인) <!--todo:2026-10-27:related-->",
            "## 개인개발",
            "- ~~이전 완료~~ (10/26 완료 확인) <!--todo:2026-10-26:99-->",
            "- 개발 작업 <!--todo:2026-10-27:2-->",
            "## 개인사",
            "- 개인 항목 <!--todo:2026-10-27:3-->",
        ]
    )
    mapping = assign_todo_numbers(parse_todo_items(content), {})
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-789",
        number_to_todo_id=mapping,
        todo_url="https://atom.example.test/#today-node",
    )[0]
    text = part.text

    assert text.index("회사일") < text.index("개인개발") < text.index("개인사") < text.index("이전 완료")
    assert text.index("연관 완료") < text.index("개인개발")
    assert "이전 완료" in text and "*99.*" not in text
    assert text.count("오늘 추가하거나 바꿀 일이 있으신가요?") == 1


def test_renderer_reuses_saved_bold_number_without_duplicate_prefix():
    content = "\n".join(
        [
            "## 회사일",
            "- **7.** ~~이미 완료된 작업~~ (10/26 완료 확인) <!--todo:2026-10-26:7-->",
        ]
    )
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-790",
        number_to_todo_id={7: "2026-10-26:7"},
        todo_url="https://atom.example.test/#today-node",
    )[0]
    rendered = "\n".join(block.get("text", {}).get("text", "") for block in part.blocks)

    assert rendered.count("*7.*") == 1
    assert "*7.* ~이미 완료된 작업~" in rendered
    buttons = [button for block in part.blocks if block["type"] == "actions" for button in block["elements"]]
    assert buttons[0]["text"]["text"] == "↺7"
    assert buttons[0]["action_id"] == "daily_todo_set_completion:7"


@pytest.mark.parametrize("ending", ["next_category", "document_end"])
def test_ten_button_boundary_does_not_emit_empty_followup_segment(ending):
    lines = [
        "## 회사일",
        "- 프로젝트 묶음 <!--todo:2026-10-27:group-->",
        *(
            f"  - 회사 작업 {number} <!--todo:2026-10-27:{number}-->"
            for number in range(1, 11)
        ),
    ]
    if ending == "next_category":
        lines.extend(
            [
                "## 개인개발",
                "- 개인 작업 <!--todo:2026-10-27:11-->",
            ]
        )
    content = "\n".join(lines)
    mapping = assign_todo_numbers(parse_todo_items(content), {})
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id=f"delivery-empty-{ending}",
        number_to_todo_id=mapping,
        todo_url="https://atom.example.test/#today-node",
    )[0]
    rendered = "\n".join(
        block.get("text", {}).get("text", "")
        for block in part.blocks
        if block["type"] == "section"
    )

    assert rendered.count("*회사일*") == 1
    assert rendered.count("• 프로젝트 묶음") == 1
    assert part.numbers == list(range(1, len(mapping) + 1))


def test_ten_child_boundary_does_not_repeat_parent_before_top_level_sibling():
    content = "\n".join(
        [
            "## 회사일",
            "- 프로젝트 묶음 <!--todo:2026-10-27:group-->",
            *(
                f"  - 하위 작업 {number} <!--todo:2026-10-27:{number}-->"
                for number in range(1, 11)
            ),
            "- 최상위 후속 작업 <!--todo:2026-10-27:11-->",
        ]
    )
    mapping = assign_todo_numbers(parse_todo_items(content), {})
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-sibling",
        number_to_todo_id=mapping,
        todo_url="https://atom.example.test/#today-node",
    )[0]
    rendered = "\n".join(
        block.get("text", {}).get("text", "")
        for block in part.blocks
        if block["type"] == "section"
    )

    assert rendered.count("• 프로젝트 묶음") == 1
    assert "• *11.* 최상위 후속 작업" in rendered
    assert part.numbers == list(range(1, 12))


def test_long_task_accessibility_labels_keep_number_and_action():
    long_title = "중요한 작업 이름 " * 12
    content = "\n".join(
        [
            "## 회사일",
            f"- {long_title}<!--todo:2026-10-27:1-->",
            f"- ~~{long_title}~~ <!--todo:2026-10-27:2-->",
        ]
    )
    part = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-long-label",
        number_to_todo_id={1: "2026-10-27:1", 2: "2026-10-27:2"},
        todo_url="https://atom.example.test/#today-node",
    )[0]
    buttons = [
        button
        for block in part.blocks
        if block["type"] == "actions"
        for button in block["elements"]
    ]
    labels = [button["accessibility_label"] for button in buttons]

    assert all(len(label) <= 75 for label in labels)
    assert labels[0].startswith("1번 ") and labels[0].endswith(" 완료 처리")
    assert labels[1].startswith("2번 ") and labels[1].endswith(" 다시 열기")


def test_long_delivery_is_split_at_block_limit_with_unique_numbers():
    content = _numbered_content(260)
    mapping = assign_todo_numbers(parse_todo_items(content), {})
    parts = render_daily_todo_messages(
        content,
        metadata={"date": "2026-10-27"},
        source_card_id="source-card",
        delivery_id="delivery-456",
        number_to_todo_id=mapping,
        todo_url="https://atom.example.test/#today-node",
    )

    assert len(parts) > 1
    assert all(len(part.blocks) <= 50 for part in parts)
    assert all(len(part.text) <= 39000 for part in parts)
    all_numbers = [number for part in parts for number in part.numbers]
    assert all_numbers == list(range(1, 261))
    assert sum(part.text.count("오늘 추가하거나 바꿀 일이 있으신가요?") for part in parts) == 1
    assert all(
        part.blocks[0]["block_id"].startswith("daily_todo_header:source-card:delivery-456:")
        for part in parts
    )
