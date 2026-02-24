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
    INTERVENTION_SENT = "intervention_sent"
    COMPLETE = "complete"
    ERROR = "error"


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
