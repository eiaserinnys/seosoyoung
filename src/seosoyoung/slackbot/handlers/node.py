"""소울스트림 노드 라우팅 관리 명령어 핸들러

오케스트레이터에서 노드 목록을 조회하여 슬랙 버튼으로 표시하고,
버튼 클릭으로 라우팅 대상을 실시간 변경합니다.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

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

    say(
        blocks=_build_node_blocks(nodes, Config.claude.soul_url),
        text="소울스트림 노드 목록",
        thread_ts=thread_ts or ts,
    )


def register_node_handlers(app):
    """노드 선택 액션 핸들러를 앱에 등록"""

    @app.action("node_select")
    def handle_node_select(ack, body, client):
        ack()

        action = body["actions"][0]
        value = json.loads(action["value"])
        new_url = f"http://{value['host']}:{value['port']}"

        env_saved = _update_soul_url(new_url)

        # 노드 목록 재조회하여 블록 갱신
        try:
            nodes = _fetch_orch_nodes(
                Config.orchestrator.url, Config.orchestrator.token,
            )
            blocks = _build_node_blocks(nodes, Config.claude.soul_url)

            if not env_saved:
                blocks.append({
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": ":warning: .env 파일을 찾을 수 없어 메모리에만 반영되었습니다.",
                    }],
                })

            # 원래 메시지를 갱신
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


def _build_node_blocks(nodes: list[dict], current_url: str) -> list[dict]:
    """노드 목록을 슬랙 Block Kit 블록으로 변환

    Args:
        nodes: 노드 딕셔너리 리스트
        current_url: 현재 라우팅 중인 soul_url

    Returns:
        슬랙 블록 리스트
    """
    current_node_id = _find_current_node_id(nodes, current_url)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "소울스트림 노드"},
        },
    ]

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
            "value": json.dumps({
                "nodeId": node_id,
                "host": node["host"],
                "port": node["port"],
            }),
        }
        if node_id == current_node_id:
            button["style"] = "primary"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
            "accessory": button,
        })

    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"현재 라우팅: {current_url}",
        }],
    })

    return blocks


_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _find_current_node_id(nodes: list[dict], current_url: str) -> str | None:
    """현재 URL에 매칭되는 노드 ID 반환

    1차: host:port 정확 비교
    2차: URL이 localhost/127.0.0.1이면 port만 비교, 후보 1개일 때 반환

    Args:
        nodes: 노드 딕셔너리 리스트
        current_url: 현재 soul_url

    Returns:
        매칭된 nodeId 또는 None
    """
    parsed = urlparse(current_url)
    target_host = parsed.hostname or ""
    target_port = parsed.port

    # 1차: 정확 매칭
    for node in nodes:
        if node["host"] == target_host and node["port"] == target_port:
            return node["nodeId"]

    # 2차: localhost 폴백
    if target_host in _LOCALHOST_HOSTS:
        candidates = [n for n in nodes if n["port"] == target_port]
        if len(candidates) == 1:
            return candidates[0]["nodeId"]

    return None


def _update_soul_url(new_url: str) -> bool:
    """soul_url을 메모리와 .env에 갱신

    Args:
        new_url: 새 soul URL

    Returns:
        .env 파일에 성공적으로 기록되었는지 여부
    """
    Config.claude.soul_url = new_url
    os.environ["SEOSOYOUNG_SOUL_URL"] = new_url

    env_path = find_dotenv(usecwd=True)
    if not env_path:
        return False

    result = set_key(env_path, "SEOSOYOUNG_SOUL_URL", new_url)
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
