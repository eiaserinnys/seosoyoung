"""소울스트림 노드 라우팅 관리 명령어 핸들러

오케스트레이터에서 노드 목록을 조회하여 슬랙 버튼으로 표시하고,
버튼 클릭으로 preferred_node를 설정하여 라우팅 대상을 변경합니다.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from dotenv import find_dotenv, set_key

from seosoyoung.slackbot.config import Config

logger = logging.getLogger(__name__)


# ── 공개 핸들러 ──────────────────────────────────────────────────


def handle_node(*, say, ts, thread_ts, user_id, client, check_permission, **_):
    """노드 명령어 핸들러 -- 소울스트림 노드 목록 표시"""
    if not check_permission(user_id, client):
        say(text="관리자 권한이 필요합니다.", thread_ts=thread_ts or ts)
        return

    if not Config.orchestrator.url:
        say(
            text="오케스트레이터 설정이 없습니다. `SOULSTREAM_ORCH_URL`을 설정해주세요.",
            thread_ts=thread_ts or ts,
        )
        return

    try:
        nodes = _fetch_orch_nodes(Config.orchestrator.url, Config.orchestrator.token)
    except Exception as e:
        say(
            text=f"오케스트레이터에 연결할 수 없습니다: {e}",
            thread_ts=thread_ts or ts,
        )
        return

    if not nodes:
        say(text="연결된 노드가 없습니다.", thread_ts=thread_ts or ts)
        return

    current_node_id = Config.orchestrator.preferred_node or None
    say(
        blocks=_build_node_blocks(nodes, current_node_id),
        text="소울스트림 노드 목록",
        thread_ts=thread_ts or ts,
    )


def register_node_handlers(app):
    """노드 선택 액션 핸들러를 앱에 등록"""

    @app.action("node_select")
    def handle_node_select(ack, body, client):
        ack()

        action = body["actions"][0]
        node_id = action["value"]
        env_saved = _update_preferred_node(node_id)

        _refresh_node_message(body, client, env_saved)

    @app.action("node_select_auto")
    def handle_node_select_auto(ack, body, client):
        ack()

        env_saved = _update_preferred_node(None)

        _refresh_node_message(body, client, env_saved)


def _refresh_node_message(body: dict, client, env_saved: bool) -> None:
    """노드 목록 재조회 후 슬랙 메시지 갱신"""
    try:
        nodes = _fetch_orch_nodes(
            Config.orchestrator.url, Config.orchestrator.token,
        )
        current_node_id = Config.orchestrator.preferred_node or None
        blocks = _build_node_blocks(nodes, current_node_id)

        if not env_saved:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": ":warning: .env 파일을 찾을 수 없어 메모리에만 반영되었습니다.",
                }],
            })

        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]
        client.chat_update(
            channel=channel,
            ts=message_ts,
            blocks=blocks,
            text="소울스트림 노드 목록",
        )
    except Exception as e:
        logger.error(f"노드 선택 후 블록 갱신 실패: {e}")


# ── 내부 함수 ────────────────────────────────────────────────────


def _fetch_orch_nodes(url: str, token: str) -> list[dict]:
    """오케스트레이터에서 노드 목록 조회

    Args:
        url: 오케스트레이터 기본 URL
        token: Bearer 인증 토큰 (빈 문자열이면 헤더 생략)

    Returns:
        노드 딕셔너리 리스트
    """
    endpoint = f"{url}/api/nodes"
    req = urllib.request.Request(endpoint)
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    return data.get("nodes", [])


def _build_node_blocks(nodes: list[dict], current_node_id: Optional[str]) -> list[dict]:
    """노드 목록을 슬랙 Block Kit 블록으로 변환

    Args:
        nodes: 노드 딕셔너리 리스트
        current_node_id: 현재 preferred_node 설정값 (None이면 자동 라우팅)

    Returns:
        슬랙 블록 리스트
    """
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "소울스트림 노드"},
        },
    ]

    # 자동 라우팅 버튼
    auto_button: dict = {
        "type": "button",
        "text": {"type": "plain_text", "text": "자동"},
        "action_id": "node_select_auto",
    }
    if current_node_id is None:
        auto_button["style"] = "primary"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*자동*  \u00b7  최소 세션 노드에 자동 배정",
        },
        "accessory": auto_button,
    })

    for node in nodes:
        node_id = node["nodeId"]
        session_count = node.get("sessionCount", 0)
        connected_at = node.get("connectedAt", "")
        rel_time = _relative_time(connected_at) if connected_at else "알 수 없음"

        text = f"*{node_id}*  \u00b7  세션 {session_count}개  \u00b7  접속 {rel_time}"

        button: dict = {
            "type": "button",
            "text": {"type": "plain_text", "text": node_id},
            "action_id": "node_select",
            "value": node_id,
        }
        if node_id == current_node_id:
            button["style"] = "primary"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
            "accessory": button,
        })

    if current_node_id:
        routing_text = f"현재 라우팅: *{current_node_id}* (고정)"
    else:
        routing_text = "현재 라우팅: *자동* (최소 세션 노드)"

    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": routing_text,
        }],
    })

    return blocks


def _update_preferred_node(node_id: Optional[str]) -> bool:
    """preferred_node를 메모리와 .env에 갱신

    Args:
        node_id: 노드 ID (None이면 자동 라우팅으로 전환)

    Returns:
        .env 파일에 성공적으로 기록되었는지 여부
    """
    value = node_id or ""
    Config.orchestrator.preferred_node = value
    os.environ["SOULSTREAM_PREFERRED_NODE"] = value

    env_path = find_dotenv(usecwd=True)
    if not env_path:
        return False

    result = set_key(env_path, "SOULSTREAM_PREFERRED_NODE", value)
    return result[0] is True


def _relative_time(iso_string: str) -> str:
    """ISO 8601 시간을 한국어 상대 시간으로 변환

    Args:
        iso_string: ISO 8601 형식 시간 문자열

    Returns:
        '방금 전', '5분 전', '2시간 전', '3일 전' 등
    """
    try:
        dt = datetime.fromisoformat(iso_string)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return "방금 전"

        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}분 전"

        hours = minutes // 60
        if hours < 24:
            return f"{hours}시간 전"

        days = hours // 24
        return f"{days}일 전"
    except (ValueError, TypeError):
        return "알 수 없음"
