"""
Pydantic 모델 - Request/Response 스키마
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


# === Enums ===

class SSEEventType(str, Enum):
    """SSE 이벤트 타입"""
    PROGRESS = "progress"
    MEMORY = "memory"
    SESSION = "session"
    INTERVENTION_SENT = "intervention_sent"
    DEBUG = "debug"
    COMPLETE = "complete"
    ERROR = "error"
    # 세분화 이벤트 (dashboard용)
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    RESULT = "result"


# === Request Models ===

class InterveneRequest(BaseModel):
    """개입 메시지 요청 (Task API 호환)"""
    text: str = Field(..., description="메시지 텍스트")
    user: str = Field(..., description="요청한 사용자")
    attachment_paths: Optional[List[str]] = Field(None, description="첨부 파일 경로 목록")


# === Response Models ===

class InterveneResponse(BaseModel):
    """개입 메시지 응답"""
    queued: bool
    queue_position: int


class AttachmentUploadResponse(BaseModel):
    """첨부 파일 업로드 응답"""
    path: str
    filename: str
    size: int
    content_type: str


class AttachmentCleanupResponse(BaseModel):
    """첨부 파일 정리 응답"""
    cleaned: bool
    files_removed: int


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    version: str
    uptime_seconds: int
    environment: Optional[str] = None


# === Error Response ===

class ErrorDetail(BaseModel):
    """에러 상세 정보"""
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """에러 응답"""
    error: ErrorDetail


# === SSE Event Models ===

class SessionEvent(BaseModel):
    """세션 ID 조기 통지 이벤트

    Claude Code 세션이 시작되면 session_id를 클라이언트에 즉시 알립니다.
    클라이언트는 이 session_id로 인터벤션 API를 호출할 수 있습니다.
    """
    type: str = "session"
    session_id: str


class ProgressEvent(BaseModel):
    """진행 상황 이벤트"""
    type: str = "progress"
    text: str


class MemoryEvent(BaseModel):
    """메모리 사용량 이벤트"""
    type: str = "memory"
    used_gb: float
    total_gb: float
    percent: float


class InterventionSentEvent(BaseModel):
    """개입 메시지 전송 확인 이벤트"""
    type: str = "intervention_sent"
    user: str
    text: str


class CompleteEvent(BaseModel):
    """실행 완료 이벤트"""
    type: str = "complete"
    result: str
    attachments: List[str] = Field(default_factory=list)
    claude_session_id: Optional[str] = Field(None, description="Claude Code 세션 ID (다음 쿼리에서 resume용)")


class ErrorEvent(BaseModel):
    """오류 이벤트"""
    type: str = "error"
    message: str
    error_code: Optional[str] = Field(None, description="에러 코드 (예: SESSION_NOT_FOUND)")


class ContextUsageEvent(BaseModel):
    """컨텍스트 사용량 이벤트"""
    type: str = "context_usage"
    used_tokens: int = Field(..., description="사용된 토큰 수")
    max_tokens: int = Field(..., description="최대 토큰 수")
    percent: float = Field(..., description="사용 퍼센트 (0-100)")


class CompactEvent(BaseModel):
    """컴팩트 실행 이벤트"""
    type: str = "compact"
    trigger: str = Field(..., description="트리거 타입 (manual 또는 auto)")
    message: str = Field(..., description="컴팩트 상태 메시지")


class DebugEvent(BaseModel):
    """디버그 정보 이벤트 (rate_limit 경고 등)"""
    type: str = "debug"
    message: str = Field(..., description="디버그 메시지")


# === Task API Models ===

class TaskStatus(str, Enum):
    """태스크 상태"""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ExecuteRequest(BaseModel):
    """실행 요청"""
    client_id: str = Field(..., description="클라이언트 ID (e.g., 'seosoyoung_bot')")
    request_id: str = Field(..., description="요청 ID (e.g., Slack thread ID)")
    prompt: str = Field(..., description="실행할 프롬프트")
    resume_session_id: Optional[str] = Field(None, description="이전 Claude 세션 ID (대화 연속성용)")
    attachment_paths: Optional[List[str]] = Field(None, description="첨부 파일 경로 목록")
    allowed_tools: Optional[List[str]] = Field(None, description="허용 도구 목록 (None이면 제한 없음)")
    disallowed_tools: Optional[List[str]] = Field(None, description="금지 도구 목록")
    use_mcp: bool = Field(True, description="MCP 서버 연결 여부")


class TaskResponse(BaseModel):
    """태스크 정보 응답"""
    client_id: str
    request_id: str
    status: TaskStatus
    result: Optional[str] = None
    error: Optional[str] = None
    claude_session_id: Optional[str] = None
    result_delivered: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None


class TaskListResponse(BaseModel):
    """태스크 목록 응답"""
    tasks: List[TaskResponse]


class TaskInterveneRequest(BaseModel):
    """개입 메시지 요청"""
    text: str = Field(..., description="메시지 텍스트")
    user: str = Field(..., description="요청한 사용자")
    attachment_paths: Optional[List[str]] = Field(None, description="첨부 파일 경로 목록")


# === 세분화 SSE Event Models (dashboard용) ===
#
# TextBlock(assistant 가시적 응답)을 "카드" 단위로 추상화합니다.
# SDK의 TextBlock은 extended thinking(ThinkingBlock)이 아닌
# assistant의 visible output 텍스트입니다.

class TextStartSSEEvent(BaseModel):
    """텍스트 블록 시작 이벤트

    AssistantMessage의 TextBlock 하나를 '카드'로 추상화하여
    시작 시점을 알립니다.
    """
    type: str = "text_start"
    card_id: str = Field(..., description="텍스트 블록 단위 카드 ID")


class TextDeltaSSEEvent(BaseModel):
    """텍스트 블록 내용 이벤트

    TextBlock의 전체 텍스트 내용. SDK가 청크 스트리밍을 지원하지
    않으므로 한 번에 전체 텍스트가 전달됩니다.
    """
    type: str = "text_delta"
    card_id: str = Field(..., description="카드 ID")
    text: str = Field(..., description="텍스트 내용")


class TextEndSSEEvent(BaseModel):
    """텍스트 블록 완료 이벤트"""
    type: str = "text_end"
    card_id: str = Field(..., description="카드 ID")


class ToolStartSSEEvent(BaseModel):
    """도구 호출 시작 이벤트"""
    type: str = "tool_start"
    card_id: Optional[str] = Field(None, description="연관된 텍스트 블록의 카드 ID")
    tool_name: str = Field(..., description="도구 이름")
    tool_input: dict = Field(default_factory=dict, description="도구 입력 파라미터")
    tool_use_id: Optional[str] = Field(None, description="SDK ToolUseBlock ID (tool_result 매칭용)")


class ToolResultSSEEvent(BaseModel):
    """도구 결과 이벤트"""
    type: str = "tool_result"
    card_id: Optional[str] = Field(None, description="연관된 텍스트 블록의 카드 ID")
    tool_name: str = Field(..., description="도구 이름")
    result: str = Field(..., description="도구 실행 결과")
    is_error: bool = Field(False, description="오류 여부")
    tool_use_id: Optional[str] = Field(None, description="SDK ToolUseBlock ID (tool_start 매칭용)")


class ResultSSEEvent(BaseModel):
    """엔진 최종 결과 이벤트 (dashboard 전용)

    CompleteEvent/ErrorEvent와 병행 발행됩니다.
    슬랙봇은 CompleteEvent/ErrorEvent를 소비하고,
    대시보드는 ResultSSEEvent를 소비합니다.
    """
    type: str = "result"
    success: bool = Field(..., description="성공 여부")
    output: str = Field(..., description="출력 텍스트")
    error: Optional[str] = Field(None, description="오류 메시지")
