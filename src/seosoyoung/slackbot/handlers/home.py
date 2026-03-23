"""App Home 핸들러

슬랙 앱 홈 탭에 소울스트림 세션 현황을 Block Kit으로 표시한다.
app_home_opened 이벤트가 발생할 때마다 소울스트림 API를 호출하여
최신 세션 정보를 가져와 렌더링한다.
"""

import logging
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

MAX_COMPLETED_SESSIONS = 5
FETCH_TIMEOUT_SECONDS = 5


def fetch_sessions(soul_url: str) -> dict:
    """소울스트림 GET /sessions를 호출하여 세션 목록을 반환한다.

    Args:
        soul_url: 소울스트림 서버 base URL (예: http://localhost:3105)

    Returns:
        {"sessions": [...], "total": int}

    Raises:
        requests.RequestException: 네트워크 오류
    """
    resp = requests.get(
        f"{soul_url}/sessions",
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _get_session_name(session: dict) -> str:
    """세션의 표시 이름을 결정한다.

    우선순위: display_name > last_message.preview > 세션 ID 뒷자리
    """
    display_name = session.get("display_name")
    if display_name:
        return display_name

    preview = (session.get("last_message") or {}).get("preview", "")
    if preview:
        # 200자 이내로 잘라서 표시
        return preview[:100] + ("…" if len(preview) > 100 else "")

    # 세션 ID 뒷 8자리
    session_id = session.get("agent_session_id", "")
    return f"sess-…{session_id[-8:]}" if len(session_id) > 8 else session_id


def _format_relative_time(iso_str: str) -> str:
    """ISO 시각 문자열을 상대 시간으로 변환한다."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        minutes = int(delta.total_seconds() / 60)

        if minutes < 1:
            return "방금 전"
        if minutes < 60:
            return f"{minutes}분 전"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}시간 전"
        days = hours // 24
        return f"{days}일 전"
    except (ValueError, TypeError):
        return "시간 정보 없음"


def _format_duration(created_at: str, updated_at: str) -> str:
    """두 ISO 시각 사이의 경과 시간을 포맷한다."""
    try:
        start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        delta = end - start
        minutes = int(delta.total_seconds() / 60)

        if minutes < 1:
            return "1분 미만"
        if minutes < 60:
            return f"{minutes}분간 실행"
        hours = minutes // 60
        remaining_mins = minutes % 60
        if remaining_mins > 0:
            return f"{hours}시간 {remaining_mins}분간 실행"
        return f"{hours}시간 실행"
    except (ValueError, TypeError):
        return "시간 정보 없음"


def _build_session_block(session: dict, is_active: bool, dashboard_base_url: str) -> dict:
    """개별 세션을 section 블록으로 변환한다."""
    session_id = session.get("agent_session_id", "")
    status = session.get("status", "")
    name = _get_session_name(session)

    # 상태 아이콘
    if status == "running":
        icon = "🟢"
    elif status in ("error", "interrupted"):
        icon = "🔴"
    else:
        icon = "✅"

    # 시간 정보
    if is_active:
        time_info = f"시작 {_format_relative_time(session.get('created_at', ''))}"
    else:
        time_info = _format_duration(
            session.get("created_at", ""),
            session.get("updated_at", ""),
        )

    # 세션 ID 축약
    short_id = f"sess-…{session_id[-8:]}" if len(session_id) > 8 else session_id

    text = f"{icon}  *{name}*\n`{short_id}`  ·  {time_info}"

    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": text,
        },
        "accessory": {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "📋 대시보드",
            },
            "url": f"{dashboard_base_url}{session_id}",
            "action_id": f"session_dashboard_{session_id[-8:]}",
        },
    }


def build_home_view(
    sessions: list[dict],
    node_name: str,
    total: int = 0,
    dashboard_base_url: str = "",
) -> dict:
    """세션 목록을 App Home Block Kit 뷰로 변환한다.

    Args:
        sessions: 소울스트림 세션 딕셔너리 목록
        node_name: 노드 이름 (헤더에 표시)
        total: 전체 세션 수
        dashboard_base_url: 소울 대시보드 base URL (예: https://soul.eiaserinnys.me/#)

    Returns:
        Block Kit home 뷰 딕셔너리
    """
    blocks: list[dict] = []

    # 헤더
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"🔮 소울스트림 세션 현황 ― {node_name}",
        },
    })

    # 갱신 시각
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"마지막 갱신: {now_str}  |  전체 세션: {total}개",
        }],
    })

    # 세션 분류: running만 실행 중, 나머지는 종료
    running_sessions = [
        s for s in sessions if s.get("status") == "running"
    ]
    error_sessions = [
        s for s in sessions
        if s.get("status") in ("error", "interrupted")
    ]
    completed_sessions = [
        s for s in sessions if s.get("status") == "completed"
    ]

    # 종료 세션(error + completed): updated_at 기준 최신순 정렬, 최대 5개
    finished_sessions = error_sessions + completed_sessions
    finished_sessions.sort(
        key=lambda s: s.get("updated_at") or "",
        reverse=True,
    )
    finished_sessions = finished_sessions[:MAX_COMPLETED_SESSIONS]

    # 실행 중 섹션
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "🟢 실행 중",
        },
    })

    if running_sessions:
        for session in running_sessions:
            blocks.append(_build_session_block(session, is_active=True, dashboard_base_url=dashboard_base_url))
    else:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "현재 실행 중인 세션이 없습니다",
            }],
        })

    # 최근 종료 섹션
    if finished_sessions:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📦 최근 종료",
            },
        })

        for session in finished_sessions:
            blocks.append(_build_session_block(session, is_active=False, dashboard_base_url=dashboard_base_url))

    # 하단 안내
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"최근 종료 세션 {len(finished_sessions)}개 표시 중  ·  탭을 다시 열면 갱신됩니다",
        }],
    })

    return {
        "type": "home",
        "blocks": blocks,
    }


def _build_error_view(error_msg: str) -> dict:
    """API 호출 실패 시 표시할 에러 뷰를 생성한다."""
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔮 소울스트림 세션 현황",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ 소울스트림 서버에 연결할 수 없습니다.\n`{error_msg}`",
                },
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": "탭을 다시 열어 재시도해 주세요.",
                }],
            },
        ],
    }


def register_home_handlers(app, dependencies: dict):
    """App Home 이벤트 핸들러를 등록한다.

    Args:
        app: Slack Bolt App 인스턴스
        dependencies: 핸들러 의존성
            - soul_url: 소울스트림 서버 URL
    """
    soul_url = dependencies.get("soul_url", "")
    dashboard_url = dependencies.get("dashboard_url", "")

    @app.event("app_home_opened")
    def handle_app_home_opened(event, client, logger):
        user_id = event.get("user")
        if not user_id:
            return

        try:
            data = fetch_sessions(soul_url)
            sessions = data.get("sessions", [])
            total = data.get("total", 0)

            # running 세션의 node_id에서 노드 이름 추출
            node_name = "unknown"
            for s in sessions:
                nid = s.get("node_id")
                if nid and s.get("status") == "running":
                    node_name = nid
                    break

            view = build_home_view(
                sessions, node_name, total=total,
                dashboard_base_url=dashboard_url,
            )
        except Exception as e:
            logger.warning(f"App Home: 소울스트림 세션 조회 실패: {e}")
            view = _build_error_view("서버 연결 실패")

        try:
            client.views_publish(user_id=user_id, view=view)
        except Exception as e:
            logger.error(f"App Home: views_publish 실패: {e}")
