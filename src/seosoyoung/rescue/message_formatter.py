"""슬랙 메시지 포맷팅 유틸리티 (rescue-bot 경량 버전)

메인 봇의 message_formatter.py에서 Trello 관련 기능을 제외한 버전입니다.
"""

from typing import Optional

# Claude 모델별 컨텍스트 윈도우 (tokens)
CONTEXT_WINDOW = 200_000


def build_context_usage_bar(usage: Optional[dict], bar_length: int = 20) -> Optional[str]:
    """usage dict에서 컨텍스트 사용량 바를 생성

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
    """
    return text.replace('`', 'ˋ')
