"""외부 session event를 Slack 스레드에 표시하는 정책."""

from __future__ import annotations

from typing import Any


_SOURCE_LABELS = {
    "browser": "[웹]",
    "web": "[웹]",
    "soul-app": "[모바일]",
    "agent": "[에이전트]",
    "api": "[API]",
    "llm": "[API]",
    "system": "[시스템]",
}


def get_caller_info(event_data: dict[str, Any]) -> dict[str, Any]:
    """SSE event payload에서 caller_info를 꺼낸다.

    soul-server Python wire는 snake_case, 일부 frontend type과 legacy payload는
    camelCase를 쓰므로 양쪽을 모두 수용한다.
    """
    caller_info = event_data.get("caller_info") or event_data.get("callerInfo") or {}
    return caller_info if isinstance(caller_info, dict) else {}


def source_label(caller_info: dict[str, Any] | None) -> str:
    if not caller_info:
        return "[외부]"
    source = caller_info.get("source")
    if not isinstance(source, str):
        return "[외부]"
    return _SOURCE_LABELS.get(source, "[외부]")


def _display_name(caller_info: dict[str, Any]) -> str:
    for key in ("display_name", "displayName", "user_id", "user"):
        value = caller_info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if caller_info.get("source") == "agent":
        for key in ("agent_name", "agent_id"):
            value = caller_info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "외부 사용자"


def _event_text(event_data: dict[str, Any]) -> str:
    for key in ("text", "content", "message", "prompt"):
        value = event_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def format_external_user_message(event_data: dict[str, Any]) -> str:
    caller_info = get_caller_info(event_data)
    return f"{source_label(caller_info)} {_display_name(caller_info)}: {_event_text(event_data)}"


def is_slack_origin_event(
    event_data: dict[str, Any],
    *,
    channel: str,
    thread_ts: str,
) -> bool:
    """같은 Slack 스레드에서 이미 보인 입력이면 echo로 본다."""
    caller_info = get_caller_info(event_data)
    if caller_info.get("source") != "slack":
        return False

    slack_info = caller_info.get("slack")
    if not isinstance(slack_info, dict):
        return True

    event_channel = slack_info.get("channel_id")
    event_thread_ts = slack_info.get("thread_ts")
    if event_channel and event_channel != channel:
        return False
    if event_thread_ts and event_thread_ts != thread_ts:
        return False
    return True


def post_external_user_message(
    client,
    *,
    channel: str,
    thread_ts: str,
    event_data: dict[str, Any],
) -> str | None:
    reply = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=format_external_user_message(event_data),
    )
    if isinstance(reply, dict):
        return reply.get("ts")
    return None
