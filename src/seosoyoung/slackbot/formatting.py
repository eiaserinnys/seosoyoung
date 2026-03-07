"""슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.
"""

import json
import os
from typing import Any, Callable, Protocol


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
THINKING_QUOTE_MAX_LEN = 500   # blockquote 표시용 thinking 텍스트 최대 길이
TOOL_INPUT_QUOTE_MAX_LEN = 300 # blockquote 표시용 tool input 값 최대 길이
TOOL_RESULT_MAX_LEN = 300      # tool result 요약 최대 길이

# 이모지 기본값 — 슬랙 표준 이모지 (프로덕션 .env에서 ssy- 커스텀으로 오버라이드)
_EMOJI_THINKING_DEFAULT = ":thought_balloon:"
_EMOJI_TOOL_DEFAULT = ":hammer:"
_EMOJI_THINKING_DONE_DEFAULT = ":white_check_mark:"
_EMOJI_TOOL_DONE_DEFAULT = ":white_check_mark:"


def _emoji_thinking() -> str:
    """thinking 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작"""
    return os.environ.get("SOULSTREAM_EMOJI_THINKING", _EMOJI_THINKING_DEFAULT)


def _emoji_tool() -> str:
    """tool 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작"""
    return os.environ.get("SOULSTREAM_EMOJI_TOOL", _EMOJI_TOOL_DEFAULT)


def _emoji_thinking_done() -> str:
    """thinking 완료 이모지"""
    return os.environ.get("SOULSTREAM_EMOJI_THINKING_DONE", _EMOJI_THINKING_DONE_DEFAULT)


def _emoji_tool_done() -> str:
    """tool 완료 이모지"""
    return os.environ.get("SOULSTREAM_EMOJI_TOOL_DONE", _EMOJI_TOOL_DONE_DEFAULT)


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

def format_initial_placeholder() -> str:
    """소울스트림 요청 전송 직후 표시할 대기 메시지"""
    return f"> {_emoji_thinking()} *소영이 생각합니다...*"


def format_thinking_initial() -> str:
    """thinking 메시지 초기 포맷"""
    return f"{_emoji_thinking()} *생각합니다...*"


def _format_thinking_body(text: str | None, emoji_fn: Callable[[], str]) -> str:
    """thinking 포맷 공통 로직 — 이모지 함수만 다름"""
    display = text.strip() if text else ""
    if not display:
        return f"{emoji_fn()} *생각합니다...*"
    if len(display) > THINKING_QUOTE_MAX_LEN:
        display = "..." + display[-THINKING_QUOTE_MAX_LEN:]
    escaped = escape_backticks(display)
    quoted = "\n".join(f"> {line}" for line in escaped.split("\n"))
    return f"{emoji_fn()} *생각합니다...*\n{quoted}"


def format_thinking_text(text: str | None) -> str:
    """thinking 메시지 텍스트 갱신 포맷

    이모지 + bold 헤더 + blockquote로 thinking 내용을 표시합니다.
    길이 초과 시 뒤에서 잘라서 최신 내용을 표시합니다.
    """
    return _format_thinking_body(text, _emoji_thinking)


def format_thinking_complete(text: str | None) -> str:
    """thinking 완료 포맷 — done 이모지로 교체한 최종 상태

    빈 텍스트도 처리하므로 호출자는 text_buffer 유무를 검사하지 않고
    항상 format_thinking_complete(text) 호출 가능.
    """
    return _format_thinking_body(text, _emoji_thinking_done)


def _format_tool_input_readable(tool_input: Any) -> str:
    """tool_input을 human-readable blockquote로 변환

    dict이면 key/value 쌍을 개별 줄로 나열하고,
    그 외에는 str 변환 후 단일 blockquote로 표시합니다.
    """
    if tool_input is None:
        return ""
    if not isinstance(tool_input, dict):
        s = str(tool_input)
        if len(s) > TOOL_INPUT_QUOTE_MAX_LEN:
            s = s[:TOOL_INPUT_QUOTE_MAX_LEN] + "..."
        return f"> {escape_backticks(s)}"

    lines: list[str] = []
    for key, value in tool_input.items():
        val_str = str(value) if not isinstance(value, str) else value
        if len(val_str) > TOOL_INPUT_QUOTE_MAX_LEN:
            val_str = val_str[:TOOL_INPUT_QUOTE_MAX_LEN] + "..."
        escaped_val = escape_backticks(val_str)
        lines.append(f"> *{escape_backticks(str(key))}*")
        lines.append(f"> {escaped_val}")
        lines.append(">")
    # 마지막 빈 > 제거
    if lines and lines[-1] == ">":
        lines.pop()
    return "\n".join(lines)


def format_tool_initial(tool_name: str, tool_input: Any = None) -> str:
    """tool 메시지 초기 포맷

    이모지 + bold tool_name 헤더를 표시하고,
    tool_input이 있으면 human-readable blockquote로 key/value를 나열합니다.
    """
    header = f"{_emoji_tool()} *{tool_name}*"
    if tool_input:
        readable = _format_tool_input_readable(tool_input)
        if readable:
            return f"{header}\n{readable}"
    return header


def _stringify_result(result: Any) -> str:
    """result를 읽기 쉬운 문자열로 변환"""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def format_tool_result(tool_name: str, result: Any, is_error: bool = False) -> str:
    """tool result 도착 시 표시 포맷

    성공 시 done 이모지 + 결과 blockquote,
    에러 시 :x: + 에러 메시지 blockquote.
    """
    if is_error:
        raw = str(result)
        result_str = raw[:TOOL_RESULT_MAX_LEN] + ("..." if len(raw) > TOOL_RESULT_MAX_LEN else "")
        escaped = escape_backticks(result_str)
        quoted = "\n".join(f"> {line}" for line in escaped.split("\n"))
        return f":x: *{tool_name}*\n{quoted}"

    result_str = _stringify_result(result)
    if len(result_str) > TOOL_RESULT_MAX_LEN:
        result_str = result_str[:TOOL_RESULT_MAX_LEN] + "..."
    if result_str:
        escaped = escape_backticks(result_str)
        quoted = "\n".join(f"> {line}" for line in escaped.split("\n"))
        return f"{_emoji_tool_done()} *{tool_name}*\n{quoted}"
    return f"{_emoji_tool_done()} *{tool_name}*"


def format_tool_complete(tool_name: str) -> str:
    """tool 메시지 완료 포맷 (결과 없이 이름만)"""
    return f"{_emoji_tool_done()} *{tool_name}*"


def format_tool_error(tool_name: str, error: str) -> str:
    """tool 메시지 에러 포맷"""
    escaped_error = escape_backticks(error)
    quoted = "\n".join(f"> {line}" for line in escaped_error.split("\n"))
    return f":x: *{tool_name}*\n{quoted}"
