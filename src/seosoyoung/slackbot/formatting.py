"""슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.
"""

import json
import os
from typing import Any, Protocol


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
_TOOL_INPUT_MAX_LEN = 200

# 이벤트 이모지 기본값 (슬랙 유니코드 폴백)
_EMOJI_THINKING_DEFAULT = "\U0001f4ad"
_EMOJI_TOOL_DEFAULT = "\U0001f527"


def _emoji_thinking() -> str:
    """thinking 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작"""
    return os.environ.get("SOULSTREAM_EMOJI_THINKING", _EMOJI_THINKING_DEFAULT)


def _emoji_tool() -> str:
    """tool 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작"""
    return os.environ.get("SOULSTREAM_EMOJI_TOOL", _EMOJI_TOOL_DEFAULT)


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
    return f"{_emoji_thinking()} *생각합니다...*"


def format_thinking_text(text: str) -> str:
    """thinking 메시지 텍스트 갱신 포맷

    이모지 + bold 헤더 + code block으로 thinking 내용을 표시합니다.
    슬랙에서 code block은 길어지면 자동 접힘(collapse)이 되어 스레드를 깔끔하게 유지합니다.

    code block 내부에서 triple backtick(```)이 나타나면 외부 fence를 닫아 포맷이 깨지므로,
    내부의 triple backtick은 유사 문자로 이스케이프합니다.
    """
    if len(text) > PROGRESS_MAX_LEN:
        text = "...\n" + text[-PROGRESS_MAX_LEN:]
    # code block 내부의 triple backtick만 이스케이프 (single/double은 안전)
    escaped = text.replace("```", "ˋˋˋ")
    return f"{_emoji_thinking()} *생각합니다...*\n```\n{escaped}\n```"


def _summarize_tool_input(tool_input: Any) -> str:
    """tool_input을 간결한 한 줄 문자열로 요약

    dict이면 주요 필드를 compact JSON으로,
    그 외에는 str 변환 후 truncate합니다.
    """
    if tool_input is None:
        return ""
    if isinstance(tool_input, dict):
        try:
            compact = json.dumps(tool_input, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            compact = str(tool_input)
    else:
        compact = str(tool_input)
    if len(compact) > _TOOL_INPUT_MAX_LEN:
        compact = compact[:_TOOL_INPUT_MAX_LEN] + "..."
    return compact


def format_tool_initial(tool_name: str, tool_input: Any = None) -> str:
    """tool 메시지 초기 포맷

    이모지 + bold tool_name 헤더를 표시하고,
    tool_input이 있으면 blockquote로 요약을 덧붙입니다.
    """
    header = f"{_emoji_tool()} *{tool_name}*"
    if tool_input:
        summary = _summarize_tool_input(tool_input)
        if summary:
            return f"{header}\n> {summary}"
    return header


def format_tool_complete(tool_name: str) -> str:
    """tool 메시지 완료 포맷 (keep 모드)"""
    return f"{_emoji_tool()} *{tool_name}* (done)"


def format_tool_error(tool_name: str, error: str) -> str:
    """tool 메시지 에러 포맷 (keep 모드)"""
    escaped_error = escape_backticks(error)
    return f"{_emoji_tool()} *{tool_name}* :x: {escaped_error}"
