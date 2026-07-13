"""Soulstream debug 이벤트의 Slack 게시 허용 정책."""

import re


_KOREAN_USAGE_WARNING = re.compile(r"⚠️ .+ 사용량 중 \d+%를 넘었습니다")


def is_user_facing_debug_message(message: str) -> bool:
    """사용자가 대응해야 하는 레거시 rate-limit 경고만 허용한다."""
    stripped = message.strip()
    normalized = stripped.casefold()

    if normalized.startswith("rate limit warning:"):
        return True
    if normalized.startswith("⚠️ rate_limit"):
        return True
    return _KOREAN_USAGE_WARNING.fullmatch(stripped) is not None
