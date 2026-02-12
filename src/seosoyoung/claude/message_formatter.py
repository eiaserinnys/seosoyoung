"""슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
"""

import re
from typing import Optional

from seosoyoung.trello.watcher import TrackedCard

# Claude 모델별 컨텍스트 윈도우 (tokens)
CONTEXT_WINDOW = 200_000


def build_context_usage_bar(usage: Optional[dict], bar_length: int = 20) -> Optional[str]:
    """usage dict에서 컨텍스트 사용량 바를 생성

    Args:
        usage: ResultMessage.usage dict (input_tokens, output_tokens 등)
        bar_length: 바의 전체 칸 수

    Returns:
        "Context | ■■■■■■□□□□□□□□□□□□□□ | 30%" 형태 문자열, 또는 None
    """
    if not usage:
        return None

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens

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
    마커 제거 후 빈 줄만 남으면 해당 줄도 삭제.

    Args:
        response: Claude 응답 텍스트

    Returns:
        마커가 제거된 텍스트
    """
    # 마커 태그만 제거 (내용은 유지)
    result = re.sub(r'<!-- SUMMARY -->\s*', '', response)
    result = re.sub(r'\s*<!-- /SUMMARY -->', '', result)
    result = re.sub(r'<!-- DETAILS -->\s*', '', result)
    result = re.sub(r'\s*<!-- /DETAILS -->', '', result)

    # 빈 줄만 남은 경우 정리 (연속된 빈 줄을 하나로)
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)

    return result.strip()


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
