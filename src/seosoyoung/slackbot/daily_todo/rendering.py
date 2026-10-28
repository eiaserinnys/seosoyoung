"""Render daily TODO cards as interactive Slack Block Kit messages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from seosoyoung.slackbot.daily_todo.parser import (
    DailyTodoFormatError,
    TodoItem,
    parse_daily_todo_card,
    parse_todo_items,
    strip_task_number_prefix,
)
from seosoyoung.slackbot.formatting import markdown_to_mrkdwn


MAX_BLOCKS = 50
MAX_SECTION_CHARS = 3000
MAX_MESSAGE_TEXT_CHARS = 39000
MAX_FALLBACK_TEXT_CHARS = 4000
MAX_ACTIONS = 10
MAX_ACCESSIBILITY_LABEL_CHARS = 75
ACTION_ID_PREFIX = "daily_todo_set_completion:"
_LIST_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<body>.*)$")
_TODO_MARKER_RE = re.compile(r"<!--\s*todo:[^>]+?\s*-->", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
_CATEGORY_RE = re.compile(r"^\s*##\s+(.+?)\s*#*\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True)
class RenderedDailyTodoPart:
    text: str
    blocks: list[dict[str, Any]]
    numbers: list[int]


@dataclass
class _Segment:
    lines: list[str]
    buttons: list[dict[str, Any]]
    numbers: list[int]


def render_daily_todo_messages(
    content: str,
    *,
    metadata: Mapping[str, Any],
    source_card_id: str,
    delivery_id: str,
    number_to_todo_id: Mapping[int | str, str],
    todo_url: str,
    include_actions: bool = True,
) -> list[RenderedDailyTodoPart]:
    """Build Block Kit messages with stable IDs and message-scoped actions."""
    if not source_card_id or not delivery_id or not todo_url:
        raise ValueError("source_card_id, delivery_id and todo_url are required")
    date = metadata.get("date")
    if not isinstance(date, str) or not date:
        raise DailyTodoFormatError("daily-todo metadata date is required")

    try:
        parsed = parse_daily_todo_card(content)
        markdown = parsed.content_before_metadata
    except DailyTodoFormatError:
        markdown = content

    items = parse_todo_items(markdown)
    item_by_line = {item.line_index: item for item in items}
    number_by_id = {todo_id: int(number) for number, todo_id in number_to_todo_id.items()}
    if len(number_by_id) != len(number_to_todo_id):
        raise ValueError("a TODO ID cannot have multiple active numbers")

    group_lines = _group_line_indices(markdown)
    segments: list[_Segment] = []
    category_order: list[str] = []
    completed_rows: dict[str, list[str]] = {}
    current_category = ""
    current_lines: list[str] = []
    current_buttons: list[dict[str, Any]] = []
    current_numbers: list[int] = []
    ancestors: list[tuple[int, str]] = []
    pending_headings: list[str] = []
    current_has_content = False
    before_first_category = True

    def start_segment() -> None:
        nonlocal current_lines
        current_lines = [f"*{current_category}*"] if current_category else []
        current_lines.extend(line for _, line in ancestors)

    def flush_segment() -> None:
        nonlocal current_lines, current_buttons, current_numbers, current_has_content
        if current_has_content and (current_lines or current_buttons):
            segments.append(_Segment(current_lines, current_buttons, current_numbers))
        current_lines = []
        current_buttons = []
        current_numbers = []
        current_has_content = False

    lines = markdown.splitlines()
    for line_index, original_line in enumerate(lines):
        if "<!-- daily-todo" in original_line.lower():
            break

        category_match = _CATEGORY_RE.match(original_line)
        if category_match:
            before_first_category = False
            flush_segment()
            current_category = category_match.group(1).strip().strip("*`")
            if current_category not in category_order:
                category_order.append(current_category)
            ancestors = []
            pending_headings = []
            continue

        if before_first_category and not _LIST_RE.match(original_line):
            original_line = _remove_preamble_duplicates(original_line, date=date, todo_url=todo_url)

        heading_match = _HEADING_RE.match(original_line)
        if heading_match:
            heading = f"*{heading_match.group(1).strip()}*"
            if current_has_content:
                current_lines.append(heading)
            else:
                pending_headings.append(heading)
            continue

        list_match = _LIST_RE.match(original_line)
        item = item_by_line.get(line_index)
        if list_match:
            indent = len(list_match.group("indent"))
            if (
                item
                and item.is_completed
                and not item.is_blocked
                and item.todo_id not in number_by_id
                and indent == 0
                and line_index not in group_lines
            ):
                completed_rows.setdefault(current_category, []).append(
                    _render_list_line(original_line, item=item, number=None)
                )
                continue
            while ancestors and ancestors[-1][0] >= indent:
                ancestors.pop()
            if not current_has_content:
                start_segment()
                current_lines.extend(pending_headings)
                pending_headings = []

            number = number_by_id.get(item.todo_id) if item else None
            actionable = bool(
                item
                and number is not None
                and not item.is_group
                and not item.is_blocked
            )
            if actionable and len(current_buttons) >= MAX_ACTIONS:
                flush_segment()

            rendered_line = _render_list_line(
                original_line,
                item=item,
                number=number if actionable else None,
            )
            current_lines.append(rendered_line)
            current_has_content = True

            if actionable and item is not None and number is not None:
                target_state = "reopen" if item.is_completed else "complete"
                current_buttons.append(
                    _button(
                        item=item,
                        number=number,
                        target_state=target_state,
                        source_card_id=source_card_id,
                        delivery_id=delivery_id,
                    )
                )
                current_numbers.append(number)

            if line_index in group_lines:
                ancestors.append((indent, rendered_line))
            if len(current_buttons) == MAX_ACTIONS:
                flush_segment()
            continue

        clean_line = _strip_comments(original_line).rstrip()
        if clean_line.strip():
            if not current_has_content:
                start_segment()
                current_lines.extend(pending_headings)
                pending_headings = []
            current_lines.append(markdown_to_mrkdwn(clean_line))
            current_has_content = True

    flush_segment()
    archived_completed = [category for category in category_order if completed_rows.get(category)]
    if archived_completed:
        archived_lines = ["*이전 완료*"]
        for category in archived_completed:
            archived_lines.append(f"*{category}*")
            archived_lines.extend(completed_rows[category])
        segments.append(_Segment(archived_lines, [], []))

    header_text = "*일일 TODO*"
    header_template = {"type": "section", "text": {"type": "mrkdwn", "text": header_text}}
    footer_date = f"{_short_date(date)} 확인"
    footer_link = f"<{todo_url}|오늘 TODO>"
    footer_guidance = "오늘 추가하거나 바꿀 일이 있으신가요?"
    fallback_text = "\n".join(
        [
            header_text,
            footer_date,
            footer_link,
            "회사일",
            "개인개발",
            "개인사",
        ]
    )
    units = [_segment_units(segment, include_actions=include_actions) for segment in segments]
    flat_units = [unit for group_units in units for unit in group_units]
    footer_text = "\n".join([footer_date, footer_link, footer_guidance])
    footer = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": footer_text,
        },
    }
    flat_units.append(([footer], []))

    parts: list[RenderedDailyTodoPart] = []
    part_blocks = [_header_block(header_template, source_card_id, delivery_id, 1)]
    part_numbers: list[int] = []
    part_text_chars = len(header_text)
    part_index = 1
    for unit_blocks, unit_numbers in flat_units:
        if len(unit_blocks) > MAX_BLOCKS - 1:
            raise DailyTodoFormatError("one TODO group exceeds Slack's message block limit")
        unit_text_chars = _text_char_count(unit_blocks)
        if (
            len(part_blocks) + len(unit_blocks) > MAX_BLOCKS
            or part_text_chars + unit_text_chars > MAX_MESSAGE_TEXT_CHARS
        ):
            parts.append(
                _make_part(
                    part_blocks,
                    part_numbers,
                    fallback_text=fallback_text,
                    footer_text=footer_text,
                    footer_guidance=footer_guidance,
                )
            )
            part_index += 1
            part_blocks = [_header_block(header_template, source_card_id, delivery_id, part_index)]
            part_numbers = []
            part_text_chars = len(header_text)
        if part_text_chars + unit_text_chars > MAX_MESSAGE_TEXT_CHARS:
            raise DailyTodoFormatError("one TODO group exceeds Slack's message text limit")
        part_blocks.extend(unit_blocks)
        part_numbers.extend(unit_numbers)
        part_text_chars += unit_text_chars
    parts.append(
        _make_part(
            part_blocks,
            part_numbers,
            fallback_text=fallback_text,
            footer_text=footer_text,
            footer_guidance=footer_guidance,
        )
    )
    return parts


def _remove_preamble_duplicates(line: str, *, date: str, todo_url: str) -> str:
    url = re.escape(todo_url)
    line = re.sub(r"\[[^\]]*\]\(" + url + r"\)", "", line)
    line = re.sub(r"<" + url + r"(?:\|[^>]*)?>", "", line)
    line = re.sub(r"(?<!\S)" + url + r"(?!\S)", "", line)
    dates = f"{re.escape(date)}|{re.escape(_short_date(date))}"
    return re.sub(r"(?<![\w/\-])(?:" + dates + r")(?![\w/\-])(?:\s*확인)?", "", line).strip()


def _group_line_indices(markdown: str) -> set[int]:
    list_rows: list[tuple[int, int]] = []
    for line_index, line in enumerate(markdown.splitlines()):
        match = _LIST_RE.match(line)
        if match:
            list_rows.append((line_index, len(match.group("indent"))))
    groups: set[int] = set()
    for position, (line_index, indent) in enumerate(list_rows):
        for next_index, next_indent in list_rows[position + 1 :]:
            if next_indent <= indent:
                break
            groups.add(line_index)
            break
    return groups


def _render_list_line(line: str, *, item: TodoItem | None, number: int | None) -> str:
    match = _LIST_RE.match(line)
    assert match is not None
    body = strip_task_number_prefix(_strip_comments(match.group("body")).strip())
    body = markdown_to_mrkdwn(body)
    prefix = f"*{number}.* " if number is not None else ""
    return f"{match.group('indent')}• {prefix}{body}".rstrip()


def _strip_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub("", _TODO_MARKER_RE.sub("", text)).rstrip()


def _button(
    *,
    item: TodoItem,
    number: int,
    target_state: str,
    source_card_id: str,
    delivery_id: str,
) -> dict[str, Any]:
    title = _task_title(item.text)
    label = _accessibility_label(number, title, target_state)
    payload = {
        "delivery_id": delivery_id,
        "source_card_id": source_card_id,
        "todo_id": item.todo_id,
        "number": number,
        "target_state": target_state,
    }
    return {
        "type": "button",
        "action_id": f"{ACTION_ID_PREFIX}{number}",
        "text": {"type": "plain_text", "text": f"↺{number}" if target_state == "reopen" else f"✓{number}"},
        "accessibility_label": label,
        "value": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def _accessibility_label(number: int, title: str, target_state: str) -> str:
    action = "다시 열기" if target_state == "reopen" else "완료 처리"
    prefix = f"{number}번 "
    suffix = f" {action}"
    title_budget = max(0, MAX_ACCESSIBILITY_LABEL_CHARS - len(prefix) - len(suffix))
    if len(title) <= title_budget:
        shortened_title = title
    elif title_budget:
        shortened_title = f"{title[: title_budget - 1]}…"
    else:
        shortened_title = ""
    return f"{prefix}{shortened_title}{suffix}"


def _task_title(text: str) -> str:
    title = _LINK_RE.sub(r"\1", text)
    title = re.sub(r"~~", "", title)
    title = re.sub(r"[*_`~]", "", title).strip()
    title = re.split(r"\s+(?:—|–|\()", title, maxsplit=1)[0].strip()
    return title or "할 일"


def _segment_units(
    segment: _Segment, *, include_actions: bool
) -> list[tuple[list[dict[str, Any]], list[int]]]:
    body_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
        for chunk in _split_section_text("\n".join(segment.lines))
        if chunk
    ]
    action_blocks: list[dict[str, Any]] = []
    if segment.buttons and include_actions:
        action_blocks.append({"type": "actions", "elements": segment.buttons})

    max_body_blocks = MAX_BLOCKS - 2  # header and one possible actions block
    if (
        len(body_blocks) <= max_body_blocks
        and _text_char_count(body_blocks + action_blocks) <= MAX_MESSAGE_TEXT_CHARS - 9
    ):
        return [(body_blocks + action_blocks, segment.numbers)]

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for block in body_blocks:
        text_chars = len(block["text"]["text"])
        if current and (
            len(current) >= max_body_blocks
            or current_chars + text_chars > MAX_MESSAGE_TEXT_CHARS - 9
        ):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += text_chars
    if current:
        chunks.append(current)

    units: list[tuple[list[dict[str, Any]], list[int]]] = []
    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        units.append((chunk + (action_blocks if is_last else []), segment.numbers if is_last else []))
    if not body_blocks and action_blocks:
        units.append((action_blocks, segment.numbers))
    return units


def _split_section_text(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        remaining = line
        while remaining:
            available = MAX_SECTION_CHARS - len(current) - (1 if current else 0)
            if available <= 0:
                chunks.append(current)
                current = ""
                available = MAX_SECTION_CHARS
            if len(remaining) <= available:
                current = f"{current}\n{remaining}" if current else remaining
                remaining = ""
            else:
                split_at = remaining.rfind(" ", 0, available + 1)
                if split_at < 1:
                    split_at = available
                piece = remaining[:split_at]
                current = f"{current}\n{piece}" if current else piece
                remaining = remaining[split_at:].lstrip()
                chunks.append(current)
                current = ""
    if current:
        chunks.append(current)
    return chunks


def _header_block(
    template: Mapping[str, Any], source_card_id: str, delivery_id: str, part_index: int
) -> dict[str, Any]:
    block = {"type": template["type"], "text": dict(template["text"])}
    block["block_id"] = f"daily_todo_header:{source_card_id}:{delivery_id}:{part_index}"
    return block


def _make_part(
    blocks: list[dict[str, Any]],
    numbers: Sequence[int],
    *,
    fallback_text: str,
    footer_text: str,
    footer_guidance: str,
) -> RenderedDailyTodoPart:
    text = "\n".join(
        block.get("text", {}).get("text", "")
        for block in blocks
        if block.get("type") == "section"
    )
    if len(text) > MAX_FALLBACK_TEXT_CHARS:
        had_footer = footer_text in text
        text = fallback_text
        if had_footer:
            text = f"{text}\n{footer_guidance}"
    return RenderedDailyTodoPart(text=text, blocks=blocks, numbers=list(numbers))


def _text_char_count(blocks: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        len(block.get("text", {}).get("text", ""))
        for block in blocks
        if block.get("type") == "section"
    )


def _short_date(value: str) -> str:
    match = re.fullmatch(r"\d{4}-(\d{2})-(\d{2})", value)
    if not match:
        raise DailyTodoFormatError("daily-todo metadata date must be YYYY-MM-DD")
    return f"{int(match.group(1))}/{int(match.group(2))}"
