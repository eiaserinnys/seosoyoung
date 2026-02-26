"""Claude 엔진 전용 타입 정의

엔진의 순수한 출력·설정 타입만 정의합니다.
슬랙/트렐로/OM 등 응용 계층의 개념을 포함하지 않습니다.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional


@dataclass
class EngineResult:
    """Claude Code 엔진의 순수 실행 결과

    응용 마커(update_requested, restart_requested, list_run)나
    OM 전용 필드는 포함하지 않습니다.
    """

    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None
    is_error: bool = False
    interrupted: bool = False
    usage: Optional[dict] = None
    collected_messages: list[dict] = field(default_factory=list)


@dataclass
class RoleConfig:
    """역할별 도구 접근 설정

    역할 이름("admin", "viewer")은 포함하지 않습니다.
    호출자가 역할 이름 → RoleConfig 매핑을 담당합니다.
    """

    allowed_tools: Optional[list[str]] = None
    disallowed_tools: Optional[list[str]] = None
    mcp_config_path: Optional[Path] = None


# 엔진 전용 콜백 타입
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]]
CompactCallback = Callable[[str, str], Coroutine[Any, Any, None]]
InterventionCallback = Callable[[], Coroutine[Any, Any, Optional[str]]]


class EngineEventType(Enum):
    """엔진 이벤트 타입

    Soul Dashboard가 구독하는 세분화 이벤트 종류.
    THINKING_*: 모델 사고 스트림
    TOOL_*: 도구 호출 및 결과
    RESULT: 최종 결과 (성공/실패 포함)
    STATE_CHANGE: 엔진 상태 전환 (idle → running 등)
    """

    THINKING_START = "thinking_start"
    THINKING_DELTA = "thinking_delta"
    THINKING_END = "thinking_end"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    RESULT = "result"
    STATE_CHANGE = "state_change"


@dataclass
class EngineEvent:
    """엔진에서 발행하는 단일 이벤트

    type: 이벤트 종류
    timestamp: 발행 시각 (Unix epoch, float)
    data: 이벤트별 페이로드 (dict)
      - THINKING_DELTA: {"text": str}
      - TOOL_START: {"tool_name": str, "tool_input": dict}
      - TOOL_RESULT: {"tool_name": str, "result": Any}
      - RESULT: {"success": bool, "output": str, "error": Optional[str]}
      - STATE_CHANGE: {"from_state": str, "to_state": str}
    """

    type: EngineEventType
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# 이벤트 콜백 타입 alias
# EngineEvent를 받아서 코루틴을 반환하는 비동기 콜백
EventCallback = Callable[[EngineEvent], Coroutine[Any, Any, None]]
