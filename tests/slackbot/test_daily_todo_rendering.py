import json

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
            "- ~~이전 완료~~ (10/26 완료 확인) <!--todo:2026-10-26:99-->",
            "- 명시 취소 (취소) <!--todo:2026-10-27:cancelled-->",
            "",
            "## 개인개발",
            "- 개발 설명만 있는 문맥",
            "",
            "## 개인사",
            "- 개인 항목",
        ]
    )
    return "\n".join(lines)


def test_actions_follow_at_most_ten_work_rows_and_keep_tree_context():
    content = _numbered_content(11)
    items = parse_todo_items(content)
    mapping = assign_todo_numbers(
        items,
        {"12": "2026-10-26:99"},
    )
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
    ] == [10, 2]
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
    assert [payload["number"] for payload in payloads] == list(range(13, 24)) + [12]
    assert payloads[-1]["target_state"] == "reopen"
    assert buttons[-1]["text"]["text"] == "↺12"
    assert buttons[0]["accessibility_label"].startswith("회사 작업 1")
    assert parts[0].numbers == list(range(13, 24)) + [12]
    fallback = parts[0].text
    assert fallback.count("오늘 추가하거나 바꿀 일이 있으신가요?") == 1
    assert fallback.count("https://atom.example.test/#today-node") == 1


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
