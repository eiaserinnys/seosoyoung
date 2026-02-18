"""슬랙 메시지 포맷팅 유틸리티 (rescue-bot 경량 버전)

메인 봇의 message_formatter.py에서 Trello 관련 기능을 제외한 버전입니다.
"""

import re
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


def parse_summary_details(response: str) -> tuple[str | None, str | None, str]:
    """응답에서 요약과 상세 내용을 파싱

    Args:
        response: Claude 응답 텍스트

    Returns:
        (summary, details, remainder): 요약, 상세, 나머지 텍스트
        - 마커가 없으면 (None, None, response) 반환
    """
    summary = None
    details = None
    remainder = response

    # SUMMARY 파싱
    summary_pattern = r'<!-- SUMMARY -->\s*(.*?)\s*<!-- /SUMMARY -->'
    summary_match = re.search(summary_pattern, response, re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
        remainder = re.sub(summary_pattern, '', remainder, flags=re.DOTALL)

    # DETAILS 파싱
    details_pattern = r'<!-- DETAILS -->\s*(.*?)\s*<!-- /DETAILS -->'
    details_match = re.search(details_pattern, response, re.DOTALL)
    if details_match:
        details = details_match.group(1).strip()
        remainder = re.sub(details_pattern, '', remainder, flags=re.DOTALL)

    # 나머지 정리
    remainder = remainder.strip()

    return summary, details, remainder


def strip_summary_details_markers(response: str) -> str:
    """응답에서 SUMMARY/DETAILS 마커만 제거하고 내용은 유지

    스레드 내 후속 대화에서 마커 태그를 제거할 때 사용.
    """
    result = re.sub(r'<!-- SUMMARY -->\s*', '', response)
    result = re.sub(r'\s*<!-- /SUMMARY -->', '', result)
    result = re.sub(r'<!-- DETAILS -->\s*', '', result)
    result = re.sub(r'\s*<!-- /DETAILS -->', '', result)

    # 빈 줄만 남은 경우 정리
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)

    return result.strip()
