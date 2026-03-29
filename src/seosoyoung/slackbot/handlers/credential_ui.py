"""크레덴셜 알림 및 프로필 관리 UI

소울스트림의 credential_alert 이벤트를 슬랙 게이지 바 + 프로필 선택 버튼으로 표시합니다.
프로필 저장/삭제/목록 조회를 위한 슬랙 Block Kit UI도 제공합니다.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 게이지 바 이모지
_GAUGE_FILLED = "🟧"
_GAUGE_EMPTY = "🟦"
_GAUGE_UNKNOWN = "❓"
_GAUGE_LENGTH = 10

# KST (UTC+9) — 인증 만료일 표시에 사용
_KST = timezone(timedelta(hours=9))

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


def format_expiry_date(expires_at: int | str | None) -> str:
    """인증 만료일을 포맷

    Args:
        expires_at: 만료 시각. Unix 밀리초 타임스탬프(int), ISO 8601 문자열(str), 또는 None

    Returns:
        "인증 유효 기간: :white_check_mark: 2026년 3월 6일" (유효)
        "인증 유효 기간: :warning: 2026년 3월 6일 (무효)" (만료)
        "인증 유효 기간: 알 수 없음" (None)
    """
    if expires_at is None:
        return "인증 유효 기간: 알 수 없음"

    try:
        if isinstance(expires_at, (int, float)):
            # 밀리초 → 초 변환
            ts_sec = expires_at / 1000.0
            expiry_dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
        else:
            expiry_dt = datetime.fromisoformat(str(expires_at))
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OSError):
        return "인증 유효 기간: 알 수 없음"

    # 로컬 시간(KST) 기준 날짜 표시
    local_dt = expiry_dt.astimezone(_KST)
    date_str = f"{local_dt.year}년 {local_dt.month}월 {local_dt.day}일"

    now = datetime.now(timezone.utc)
    if now < expiry_dt:
        return f"인증 유효 기간: :white_check_mark: {date_str}"
    else:
        return f"인증 유효 기간: :warning: {date_str} (무효)"


def build_credential_alert_blocks(utilization: float, rate_limit_type: str) -> list[dict]:
    """사용량 경고 Block Kit 블록 생성

    Args:
        utilization: 사용량 비율 (0~1)
        rate_limit_type: rate limit 타입 ("five_hour", "seven_day" 등)

    Returns:
        Slack Block Kit blocks
    """
    pct = int(utilization * 100)
    type_label = {"five_hour": "5시간", "seven_day": "7일"}.get(rate_limit_type, rate_limit_type)
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":warning: *사용량 경고*\n{type_label} 사용량이 {pct}%에 달했습니다.",
            },
        }
    ]


def build_credential_alert_text(utilization: float, rate_limit_type: str) -> str:
    """Block Kit의 fallback text"""
    pct = int(utilization * 100)
    type_label = {"five_hour": "5시간", "seven_day": "7일"}.get(rate_limit_type, rate_limit_type)
    return f"사용량 경고: {type_label} 사용량이 {pct}%에 달했습니다."


def send_credential_alert(
    client,
    channel: str,
    data: dict,
) -> None:
    """사용량 경고 알림을 슬랙 채널에 전송

    Args:
        client: Slack client
        channel: 알림 채널 ID
        data: credential_alert 이벤트 데이터
            - utilization: float (0~1)
            - rate_limit_type: str
    """
    global _last_alert_time

    utilization = data.get("utilization")
    rate_limit_type = data.get("rate_limit_type", "unknown")

    if utilization is None:
        logger.warning("credential_alert 데이터에 utilization 정보가 없습니다")
        return

    with _alert_lock:
        now = time.monotonic()
        if now - _last_alert_time < _ALERT_COOLDOWN:
            logger.debug("credential_alert 쿨다운 중, 무시")
            return
        _last_alert_time = now

    blocks = build_credential_alert_blocks(utilization, rate_limit_type)
    text = build_credential_alert_text(utilization, rate_limit_type)

    try:
        client.chat_postMessage(
            channel=channel,
            blocks=blocks,
            text=text,
        )
        logger.info(f"크레덴셜 알림 전송: channel={channel}, utilization={utilization:.1%}")
    except Exception as e:
        logger.error(f"크레덴셜 알림 전송 실패: {e}")
