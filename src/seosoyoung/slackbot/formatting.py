"""슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.
"""

from typing import Protocol


# --- Protocols ---

class _CardLike(Protocol):
    """포맷팅에 필요한 최소 카드 속성"""

    @property
    def card_name(self) -> str: ...

    @property
    def card_url(self) -> str: ...


# --- 상수 ---

SLACK_MSG_MAX_LEN = 3900
PROGRESS_MAX_LEN = 3800
DM_MSG_MAX_LEN = 3000


# --- 함수 ---

def escape_backticks(text: str) -> str:
    """텍스트 내 모든 백틱을 이스케이프

    슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
    텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
    모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.
    """
    return text.replace('`', 'ˋ')


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


def build_trello_header(card: _CardLike | None, session_id: str = "") -> str:
    """트렐로 카드용 슬랙 메시지 헤더 생성

    진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.
    card가 None이면 카드 정보 없이 세션 ID만 표시합니다.
    """
    session_display = f" | #️⃣ {session_id[:8]}" if session_id else ""
    if card is None:
        return f"*🎫 (카드 정보 없음){session_display}*"
    return f"*🎫 <{card.card_url}|{card.card_name}>{session_display}*"


def format_trello_progress(text: str, card: _CardLike | None, session_id: str) -> str:
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


# --- 세분화 이벤트 메시지 포맷 ---

def format_thinking_initial() -> str:
    """thinking 메시지 초기 포맷"""
    return "... (thinking)"


def format_thinking_text(text: str) -> str:
    """thinking 메시지 텍스트 갱신 포맷"""
    escaped = escape_backticks(text)
    if len(escaped) > PROGRESS_MAX_LEN:
        escaped = "...\n" + escaped[-PROGRESS_MAX_LEN:]
    return escaped


def format_tool_initial(tool_name: str) -> str:
    """tool 메시지 초기 포맷"""
    return f">> {tool_name}"


def format_tool_complete(tool_name: str) -> str:
    """tool 메시지 완료 포맷 (keep 모드)"""
    return f">> {tool_name} (done)"


def format_tool_error(tool_name: str, error: str) -> str:
    """tool 메시지 에러 포맷 (keep 모드)"""
    escaped_error = escape_backticks(error)
    return f"🔧 {tool_name} ❌ {escaped_error}"
