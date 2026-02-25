"""SDK 메시지 파싱 에러 호환 레이어

MessageParseError를 forward-compatible하게 분류하는 공통 유틸.
Agent SDK 전환 후에는 SDK 내부에서 None skip이 처리되므로
except MessageParseError 블록이 거의 트리거되지 않지만,
방어적 폴백으로 유지한다.
"""

import logging
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class ParseAction(Enum):
    """MessageParseError 처리 결과"""
    CONTINUE = auto()  # 무시하고 루프 계속
    RAISE = auto()     # 예외 재발생 (진짜 에러)


def classify_parse_error(
    data: Optional[dict],
    *,
    log_fn: Optional[logging.Logger] = None,
) -> tuple[ParseAction, Optional[str]]:
    """MessageParseError의 data를 분류하여 처리 액션을 반환.

    Args:
        data: MessageParseError.data (dict 또는 None)
        log_fn: 로거 (None이면 모듈 로거 사용)

    Returns:
        (action, msg_type): action은 CONTINUE/RAISE, msg_type은 분류된 메시지 타입
    """
    _log = log_fn or logger

    if not isinstance(data, dict):
        return ParseAction.RAISE, None

    msg_type = data.get("type")

    if msg_type == "rate_limit_event":
        rate_limit_info = data.get("rate_limit_info", {})
        status = rate_limit_info.get("status", "")

        if status == "allowed":
            pass  # 완전히 무시
        elif status == "allowed_warning":
            _log.info(
                "rate_limit allowed_warning: "
                f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                f"utilization={rate_limit_info.get('utilization')}"
            )
        else:
            # rejected, rate_limited 등
            _log.warning(
                f"rate_limit_event skip (status={status}): "
                f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                f"resetsAt={rate_limit_info.get('resetsAt')}"
            )
        return ParseAction.CONTINUE, msg_type

    if msg_type is not None:
        # 미래의 unknown type → forward-compatible skip
        _log.debug(f"Unknown message type skipped: {msg_type}")
        return ParseAction.CONTINUE, msg_type

    # type 필드조차 없는 진짜 파싱 에러
    return ParseAction.RAISE, None
