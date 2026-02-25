"""슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
- 컨텍스트 사용량 바
- 백틱 이스케이프
- 트렐로 헤더
- 진행 상황(on_progress) 포맷팅

순수 텍스트 변환 함수들은 slackbot.formatting으로 추출되었습니다.
이 모듈은 하위호환을 위해 re-export합니다.
"""

import logging
from typing import Optional

from seosoyoung.slackbot.formatting import (  # noqa: F401 — re-export
    DM_MSG_MAX_LEN,
    PROGRESS_MAX_LEN,
    SLACK_MSG_MAX_LEN,
    build_trello_header,
    escape_backticks,
    format_as_blockquote,
    format_dm_progress,
    format_trello_progress,
    truncate_progress_text,
)

logger = logging.getLogger(__name__)

# Claude 모델별 컨텍스트 윈도우 (tokens)
CONTEXT_WINDOW = 200_000


def build_context_usage_bar(usage: Optional[dict], bar_length: int = 20) -> Optional[str]:
    """usage dict에서 컨텍스트 사용량 바를 생성

    SDK의 ResultMessage.usage 구조:
    - input_tokens: 캐시 미스분 (새로 보낸 토큰)
    - cache_creation_input_tokens: 이번 턴에 새로 캐시에 쓴 토큰
    - cache_read_input_tokens: 캐시에서 읽은 토큰
    → 실제 컨텍스트 크기 = 세 값의 합

    Args:
        usage: ResultMessage.usage dict
        bar_length: 바의 전체 칸 수

    Returns:
        "Context | ■■■■■■□□□□□□□□□□□□□□ | 30%" 형태 문자열, 또는 None
    """
    if not usage:
        return None

    input_tokens = usage.get("input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    total_tokens = input_tokens + cache_creation + cache_read

    if total_tokens <= 0:
        return None

    percent = min(total_tokens / CONTEXT_WINDOW * 100, 100)
    filled = round(percent / 100 * bar_length)
    empty = bar_length - filled

    bar = "■" * filled + "□" * empty
    return f"`Context` | `{bar}` | `{percent:.0f}%`"
