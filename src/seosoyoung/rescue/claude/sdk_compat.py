"""SDK 메시지 파싱 에러 호환 레이어

MessageParseError를 forward-compatible하게 분류하는 공통 유틸.
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
    """MessageParseError의 data를 분류하여 처리 액션을 반환."""
    _log = log_fn or logger

    if not isinstance(data, dict):
        return ParseAction.RAISE, None

    msg_type = data.get("type")

    if msg_type == "rate_limit_event":
        rate_limit_info = data.get("rate_limit_info", {})
        status = rate_limit_info.get("status", "")

        if status == "allowed":
            pass
        elif status == "allowed_warning":
            _log.info(
                "rate_limit allowed_warning: "
                f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                f"utilization={rate_limit_info.get('utilization')}"
            )
        else:
            _log.warning(
                f"rate_limit_event skip (status={status}): "
                f"rateLimitType={rate_limit_info.get('rateLimitType')}, "
                f"resetsAt={rate_limit_info.get('resetsAt')}"
            )
        return ParseAction.CONTINUE, msg_type

    if msg_type is not None:
        _log.debug(f"Unknown message type skipped: {msg_type}")
        return ParseAction.CONTINUE, msg_type

    return ParseAction.RAISE, None
