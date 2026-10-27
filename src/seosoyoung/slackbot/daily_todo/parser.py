"""Read and update the Markdown and hidden JSON in a daily TODO card."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class DailyTodoFormatError(ValueError):
    """The card does not contain a readable daily-todo operations comment."""


DUPLICATE_TODO_ROW_MESSAGE = "같은 작업 행에 서로 다른 TODO ID가 연결되어 있습니다. 원문을 확인해주세요."
MISSING_TODO_ROW_MESSAGE = "TODO ID에 연결된 작업 행이나 작업명이 없습니다. 원문을 확인해주세요."


@dataclass(frozen=True)
class ParsedDailyTodoCard:
    content: str
    content_before_metadata: str
    content_after_metadata: str
    metadata: dict[str, Any]
    marker_prefix: str
    metadata_leading_whitespace: str
    metadata_trailing_whitespace: str


@dataclass(frozen=True)
class TodoItem:
    todo_id: str
    category: str
    text: str
    line_index: int
    indent: int
    is_completed: bool
    is_blocked: bool
    is_group: bool
    display_number: int | None = None


_METADATA_MARKER_RE = re.compile(r"<!--\s*daily-todo\b", re.IGNORECASE)
_TODO_ID_RE = re.compile(r"<!--\s*todo:([^>]+?)\s*-->", re.IGNORECASE)
_LIST_LINE_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<body>.*)$")
_NUMBERED_TASK_PREFIX_RE = re.compile(
    r"^(?P<leading>\s*)\*\*(?P<number>\d+)\.\*\*(?P<spacing>\s+)"
)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
_BLOCKED_RE = re.compile(r"(?:^|[\s(（])(?:보류|취소)(?:중|됨|함|$|[\s)）.,;])")


def parse_daily_todo_card(content: str) -> ParsedDailyTodoCard:
    """Parse the full card without imposing a metadata size limit."""
    marker = _METADATA_MARKER_RE.search(content)
    if marker is None:
        raise DailyTodoFormatError("daily-todo operations comment is missing")

    comment_end = content.find("-->", marker.end())
    if comment_end < 0:
        raise DailyTodoFormatError("daily-todo operations comment is not closed")

    raw_metadata = content[marker.end() : comment_end]
    leading_whitespace = raw_metadata[: len(raw_metadata) - len(raw_metadata.lstrip())]
    trailing_whitespace = raw_metadata[len(raw_metadata.rstrip()) :]
    serialized_metadata = raw_metadata.strip()
    try:
        metadata = json.loads(serialized_metadata)
    except json.JSONDecodeError as exc:
        raise DailyTodoFormatError("daily-todo operations JSON is invalid") from exc
    if not isinstance(metadata, dict):
        raise DailyTodoFormatError("daily-todo operations JSON must be an object")

    return ParsedDailyTodoCard(
        content=content,
        content_before_metadata=content[: marker.start()],
        content_after_metadata=content[comment_end + 3 :],
        metadata=metadata,
        marker_prefix=content[: marker.end()],
        metadata_leading_whitespace=leading_whitespace,
        metadata_trailing_whitespace=trailing_whitespace,
    )


def serialize_daily_todo_metadata(metadata: dict[str, Any]) -> str:
    """Serialize JSON safely inside the outer HTML comment, preserving Korean."""
    serialized = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    return serialized.replace("<", r"\u003c").replace(">", r"\u003e")


def replace_daily_todo_metadata(content: str, metadata: dict[str, Any]) -> str:
    """Replace only the JSON payload, preserving all surrounding card text."""
    parsed = parse_daily_todo_card(content)
    marker_end = _METADATA_MARKER_RE.search(content)
    assert marker_end is not None
    payload_start = marker_end.end()
    comment_end = content.find("-->", payload_start)
    safe_json = serialize_daily_todo_metadata(metadata)
    return (
        content[:payload_start]
        + parsed.metadata_leading_whitespace
        + safe_json
        + parsed.metadata_trailing_whitespace
        + "-->"
        + content[comment_end + 3 :]
    )


def parse_todo_items(content: str) -> list[TodoItem]:
    """Read ID-bearing TODO rows while retaining their Markdown tree positions."""
    lines = content.splitlines()
    list_rows: dict[int, tuple[int, str]] = {}
    item_rows: list[tuple[str, int, int, str, str, int | None]] = []
    category = ""

    for line_index, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if heading:
            category = heading.group(1).strip().strip("*`")

        list_match = _LIST_LINE_RE.match(line)
        if list_match:
            indent = len(list_match.group("indent"))
            list_rows[line_index] = (indent, list_match.group("body"))

        for todo_match in _TODO_ID_RE.finditer(line):
            row_index = line_index
            row_indent = len(line) - len(line.lstrip())
            row_body = ""
            if list_match:
                row_indent = len(list_match.group("indent"))
                row_body = line[list_match.start("body") : todo_match.start()]
            else:
                for previous_index in range(line_index - 1, -1, -1):
                    previous = lines[previous_index]
                    if _HEADING_RE.match(previous):
                        break
                    previous_list = _LIST_LINE_RE.match(previous)
                    if previous_list:
                        row_index = previous_index
                        row_indent = len(previous_list.group("indent"))
                        row_body = previous[previous_list.start("body") :]
                        break

            row_body = _TODO_ID_RE.sub("", row_body)
            row_body = re.sub(r"<!--.*?-->", "", row_body).strip()
            row_body = re.sub(r"^\[[ xX]\]\s*", "", row_body)
            display_match = _NUMBERED_TASK_PREFIX_RE.match(row_body)
            display_number = int(display_match.group("number")) if display_match else None
            if display_match:
                row_body = row_body[display_match.end() :]
            item_rows.append(
                (
                    todo_match.group(1).strip(),
                    row_index,
                    row_indent,
                    row_body,
                    category,
                    display_number,
                )
            )
            # Status is recomputed from this exact row when constructing the
            # immutable item below; keeping source text avoids ID/title guesses.

    bullet_positions = sorted(list_rows.items())
    items: list[TodoItem] = []
    seen_ids: set[str] = set()
    seen_rows: set[int] = set()
    for todo_id, row_index, indent, row_text, item_category, display_number in item_rows:
        if todo_id in seen_ids:
            raise DailyTodoFormatError(f"duplicate todo ID: {todo_id}")
        if not row_text.strip():
            raise DailyTodoFormatError(MISSING_TODO_ROW_MESSAGE)
        if row_index in seen_rows:
            raise DailyTodoFormatError(DUPLICATE_TODO_ROW_MESSAGE)
        seen_ids.add(todo_id)
        seen_rows.add(row_index)
        next_sibling = next(
            (
                candidate_index
                for candidate_index, (candidate_indent, _) in bullet_positions
                if candidate_index > row_index and candidate_indent <= indent
            ),
            len(lines),
        )
        has_child = any(
            other_index > row_index
            and other_index < next_sibling
            and other_indent > indent
            for other_id, other_index, other_indent, _, _, _ in item_rows
            if other_id != todo_id
        )
        items.append(
            TodoItem(
                todo_id=todo_id,
                category=item_category,
                text=row_text,
                line_index=row_index,
                indent=indent,
                is_completed=bool(re.search(r"~~.+?~~", row_text)),
                is_blocked=bool(_BLOCKED_RE.search(row_text)),
                is_group=has_child,
                display_number=display_number,
            )
        )
    return items


def set_task_completion(
    content: str,
    todo_id: str,
    *,
    completed: bool,
    annotation: str,
) -> str:
    """Strike or reopen one task name, leaving its memo and ID untouched."""
    lines = content.splitlines(keepends=True)
    plain_lines = [line.rstrip("\r\n") for line in lines]
    target_line_index: int | None = None
    target_match: re.Match[str] | None = None

    for line_index, line in enumerate(plain_lines):
        for todo_match in _TODO_ID_RE.finditer(line):
            if todo_match.group(1).strip() != todo_id:
                continue
            if _LIST_LINE_RE.match(line):
                target_line_index = line_index
                target_match = todo_match
            else:
                for previous_index in range(line_index - 1, -1, -1):
                    if _HEADING_RE.match(plain_lines[previous_index]):
                        break
                    if _LIST_LINE_RE.match(plain_lines[previous_index]):
                        target_line_index = previous_index
                        target_match = None
                        break
            break
        if target_line_index is not None:
            break

    if target_line_index is None:
        raise KeyError(f"todo ID not found: {todo_id}")

    original = plain_lines[target_line_index]
    if target_match is None:
        editable = original
        suffix = ""
    else:
        editable = original[: target_match.start()]
        suffix = original[target_match.start() :]

    updated = _edit_task_line(editable, completed=completed, annotation=annotation)
    line_ending = lines[target_line_index][len(plain_lines[target_line_index]) :]
    lines[target_line_index] = updated + suffix + line_ending
    return "".join(lines)


def set_task_number(content: str, todo_id: str, number: int | None) -> str:
    """Set or remove one task's display number without changing its row content."""
    if number is not None and number < 1:
        raise ValueError("TODO number must be positive")
    lines = content.splitlines(keepends=True)
    plain_lines = [line.rstrip("\r\n") for line in lines]
    target_line_index: int | None = None

    for line_index, line in enumerate(plain_lines):
        for todo_match in _TODO_ID_RE.finditer(line):
            if todo_match.group(1).strip() != todo_id:
                continue
            if _LIST_LINE_RE.match(line):
                target_line_index = line_index
            else:
                for previous_index in range(line_index - 1, -1, -1):
                    if _HEADING_RE.match(plain_lines[previous_index]):
                        break
                    if _LIST_LINE_RE.match(plain_lines[previous_index]):
                        target_line_index = previous_index
                        break
            break
        if target_line_index is not None:
            break

    if target_line_index is None:
        raise KeyError(f"todo ID not found: {todo_id}")

    original = plain_lines[target_line_index]
    list_match = _LIST_LINE_RE.match(original)
    if list_match is None:
        raise DailyTodoFormatError("TODO ID is not attached to a list row")
    body_start = list_match.start("body")
    body = original[body_start:]
    numbered = _NUMBERED_TASK_PREFIX_RE.match(body)
    if numbered:
        leading = numbered.group("leading")
        task_body = body[numbered.end() :]
    else:
        leading_length = len(body) - len(body.lstrip())
        leading = body[:leading_length]
        task_body = body[leading_length:]
    updated_body = (
        f"{leading}**{number}.** {task_body}"
        if number is not None
        else f"{leading}{task_body}"
    )
    if updated_body == body:
        return content

    line_ending = lines[target_line_index][len(original) :]
    lines[target_line_index] = original[:body_start] + updated_body + line_ending
    return "".join(lines)


def strip_task_number_prefix(text: str) -> str:
    """Return task text without an Atom display number prefix."""
    match = _NUMBERED_TASK_PREFIX_RE.match(text)
    return f"{match.group('leading')}{text[match.end():]}" if match else text


def _edit_task_line(line: str, *, completed: bool, annotation: str) -> str:
    list_match = _LIST_LINE_RE.match(line)
    if list_match is None:
        raise DailyTodoFormatError("TODO ID is not attached to a list row")

    prefix_end = list_match.start("body")
    body = line[prefix_end:]
    number_match = _NUMBERED_TASK_PREFIX_RE.match(body)
    number_prefix = body[: number_match.end()] if number_match else ""
    task_body = body[number_match.end() :] if number_match else body
    start, end, already_struck = _task_name_span(task_body)
    if completed and not already_struck:
        task_body = task_body[:start] + "~~" + task_body[start:end] + "~~" + task_body[end:]
    elif not completed and already_struck:
        task_body = task_body[:start] + task_body[start + 2 : end - 2] + task_body[end:]

    marker = f" ({annotation})" if annotation else ""
    if completed:
        if marker and not task_body.rstrip().endswith(marker):
            task_body = task_body.rstrip() + marker + task_body[len(task_body.rstrip()) :]
    elif marker and task_body.rstrip().endswith(marker):
        task_body = task_body.rstrip()[: -len(marker)] + task_body[len(task_body.rstrip()) :]
    return line[:prefix_end] + number_prefix + task_body


def _task_name_span(body: str) -> tuple[int, int, bool]:
    leading = len(body) - len(body.lstrip())
    candidate = body[leading:]
    if candidate.startswith("~~"):
        close = candidate.find("~~", 2)
        if close >= 0:
            return leading, leading + close + 2, True

    if candidate.startswith("["):
        link_end = _markdown_link_end(candidate)
        if link_end is not None:
            return leading, leading + link_end, False

    separators = [position for token in (" — ", " – ", " (", "  ") if (position := candidate.find(token)) >= 0]
    end = min(separators) if separators else len(candidate.rstrip())
    if end <= 0:
        raise DailyTodoFormatError("TODO task name is empty")
    return leading, leading + end, False


def _markdown_link_end(text: str) -> int | None:
    label_end = text.find("](")
    if label_end < 0:
        return None
    depth = 1
    index = label_end + 2
    while index < len(text):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None
