"""크레덴셜 알림 UI

소울스트림의 credential_alert 이벤트를 슬랙 게이지 바 + 프로필 선택 버튼으로 표시합니다.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 게이지 바 이모지
_GAUGE_FILLED = "🟧"
_GAUGE_EMPTY = "🟦"
_GAUGE_UNKNOWN = "❓"
_GAUGE_LENGTH = 10

# rate limit 타입 → 표시 레이블
_RATE_TYPE_LABELS = {
    "five_hour": "5시간",
    "seven_day": "주간",
}

# 알림 쿨다운 (5분) — Soul 서버 측 중복 방지 외에 봇 측 안전장치
_ALERT_COOLDOWN = 300.0
_last_alert_time: float = 0.0
_alert_lock = threading.Lock()


def render_gauge(utilization: float | str, bar_length: int = _GAUGE_LENGTH) -> str:
    """사용량을 이모지 게이지 바로 렌더링

    Args:
        utilization: 사용률 (0.0~1.0) 또는 "unknown"
        bar_length: 게이지 바 길이 (기본 10)

    Returns:
        게이지 바 문자열 (예: "🟧🟧🟧🟧🟧🟦🟦🟦🟦🟦")
    """
    if isinstance(utilization, str):
        return _GAUGE_UNKNOWN * bar_length

    filled = int(float(utilization) * bar_length)
    filled = max(0, min(filled, bar_length))
    return _GAUGE_FILLED * filled + _GAUGE_EMPTY * (bar_length - filled)


def format_time_remaining(resets_at: Optional[str]) -> str:
    """리셋까지 남은 시간을 포맷

    Args:
        resets_at: 리셋 시간 (ISO 8601) 또는 None

    Returns:
        "초기화까지 1시간 15분", "초기화 완료", 또는 ""
    """
    if not resets_at:
        return ""

    try:
        reset_dt = datetime.fromisoformat(resets_at)
        if reset_dt.tzinfo is None:
            reset_dt = reset_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ""

    now = datetime.now(timezone.utc)
    if now >= reset_dt:
        return "초기화 완료"

    remaining = reset_dt - now
    total_seconds = int(remaining.total_seconds())

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}일")
    if hours > 0:
        parts.append(f"{hours}시간")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes}분")

    if not parts:
        parts.append("1분 미만")

    return f"초기화까지 {' '.join(parts)}"


def render_rate_limit_line(
    rate_type: str,
    utilization: float | str,
    resets_at: Optional[str],
) -> str:
    """단일 rate limit 라인 렌더링

    Returns:
        "🟧🟧🟧🟧🟧🟦🟦🟦🟦🟦 5시간: 51% (초기화까지 3일 2시간)"
    """
    label = _RATE_TYPE_LABELS.get(rate_type, rate_type)
    gauge = render_gauge(utilization)

    if isinstance(utilization, str):
        return f"{_GAUGE_UNKNOWN} {label}: unknown"

    pct = int(float(utilization) * 100)
    time_str = format_time_remaining(resets_at)

    if time_str:
        return f"{gauge} {label}: {pct}% ({time_str})"
    return f"{gauge} {label}: {pct}%"


def render_profile_section(profile: dict, is_active: bool) -> str:
    """프로필 섹션 렌더링

    Args:
        profile: {"name": str, "five_hour": {...}, "seven_day": {...}}
        is_active: 활성 프로필 여부

    Returns:
        "*linegames* (활성)\\n🟧🟧... 5시간: 95%...\\n🟧🟧... 주간: 51%..."
    """
    name = profile["name"]
    header = f"*{name}*" + (" (활성)" if is_active else "")

    lines = [header]
    for rate_type in ("five_hour", "seven_day"):
        state = profile.get(rate_type, {})
        utilization = state.get("utilization", "unknown")
        resets_at = state.get("resets_at")
        lines.append(render_rate_limit_line(rate_type, utilization, resets_at))

    return "\n".join(lines)


def build_credential_alert_blocks(
    active_profile: str,
    profiles: list[dict],
) -> list[dict]:
    """크레덴셜 알림 Block Kit 블록 생성

    Args:
        active_profile: 현재 활성 프로필 이름
        profiles: 프로필별 rate limit 정보 리스트

    Returns:
        Slack Block Kit blocks
    """
    sections = []
    for profile in profiles:
        is_active = profile["name"] == active_profile
        sections.append(render_profile_section(profile, is_active))

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":warning: *크레덴셜 사용량 알림*\n\n" + "\n\n".join(sections),
            },
        },
    ]

    buttons = []
    for profile in profiles:
        name = profile["name"]
        is_active = name == active_profile
        button = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": f"{name} (현재)" if is_active else name,
            },
            "action_id": f"credential_switch_{name}",
            "value": name,
        }
        if not is_active:
            button["style"] = "primary"
        buttons.append(button)

    if buttons:
        blocks.append({
            "type": "actions",
            "block_id": "credential_switch_actions",
            "elements": buttons,
        })

    return blocks


def build_credential_alert_text(active_profile: str, profiles: list[dict]) -> str:
    """Block Kit의 fallback text"""
    sections = []
    for p in profiles:
        is_active = p["name"] == active_profile
        sections.append(render_profile_section(p, is_active))
    return "크레덴셜 사용량 알림\n\n" + "\n\n".join(sections)


def send_credential_alert(
    client,
    channel: str,
    data: dict,
) -> None:
    """크레덴셜 알림을 슬랙 채널에 전송

    Args:
        client: Slack client
        channel: 알림 채널 ID
        data: credential_alert 이벤트 데이터
    """
    global _last_alert_time

    active_profile = data.get("active_profile", "")
    profiles = data.get("profiles", [])

    if not profiles:
        logger.warning("credential_alert 데이터에 프로필 정보가 없습니다")
        return

    with _alert_lock:
        now = time.monotonic()
        if now - _last_alert_time < _ALERT_COOLDOWN:
            logger.debug("credential_alert 쿨다운 중, 무시")
            return
        _last_alert_time = now

    blocks = build_credential_alert_blocks(active_profile, profiles)
    text = build_credential_alert_text(active_profile, profiles)

    try:
        client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=text,
        )
        logger.info(f"크레덴셜 알림 전송: channel={channel}, active={active_profile}")
    except Exception as e:
        logger.error(f"크레덴셜 알림 전송 실패: {e}")
