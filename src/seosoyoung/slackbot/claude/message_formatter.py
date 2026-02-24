"""슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
- 컨텍스트 사용량 바
- 백틱 이스케이프
- 트렐로 헤더
- 진행 상황(on_progress) 포맷팅
"""

import logging
from typing import Optional

from seosoyoung.slackbot.trello.watcher import TrackedCard

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


def escape_backticks(text: str) -> str:
    """텍스트 내 모든 백틱을 이스케이프

    슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
    텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
    모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

    변환 규칙:
    - ` (모든 백틱) → ˋ (U+02CB, modifier letter grave accent)

    Args:
        text: 변환할 텍스트

    Returns:
        백틱이 이스케이프된 텍스트
    """
    return text.replace('`', 'ˋ')


def build_trello_header(card: TrackedCard, session_id: str = "") -> str:
    """트렐로 카드용 슬랙 메시지 헤더 생성

    진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

    Args:
        card: TrackedCard 정보
        session_id: 세션 ID (표시용)

    Returns:
        헤더 문자열
    """
    session_display = f" | #️⃣ {session_id[:8]}" if session_id else ""
    return f"*🎫 <{card.card_url}|{card.card_name}>{session_display}*"


# 진행 상황 메시지 길이 제한
PROGRESS_MAX_LEN = 3800
DM_MSG_MAX_LEN = 3000


def truncate_progress_text(text: str) -> str:
    """진행 상황 텍스트를 표시용으로 정리"""
    display_text = text.lstrip("\n")
    if not display_text:
        return ""
    if len(display_text) > PROGRESS_MAX_LEN:
        display_text = "...\n" + display_text[-PROGRESS_MAX_LEN:]
    return display_text


def format_as_blockquote(text: str) -> str:
    """텍스트를 슬랙 blockquote 형식으로 변환"""
    escaped = escape_backticks(text)
    lines = [f"> {line}" for line in escaped.split("\n")]
    return "\n".join(lines)


def format_trello_progress(text: str, card: TrackedCard, session_id: str) -> str:
    """트렐로 모드 채널 진행 상황 포맷"""
    header = build_trello_header(card, session_id)
    escaped = escape_backticks(text)
    return f"{header}\n\n```\n{escaped}\n```"


def format_dm_progress(text: str, max_len: int = DM_MSG_MAX_LEN) -> str:
    """DM 스레드 진행 상황 포맷 (blockquote, 길이 제한)"""
    escaped = escape_backticks(text)
    if len(escaped) > max_len:
        escaped = escaped[-max_len:]
    return format_as_blockquote(escaped)
