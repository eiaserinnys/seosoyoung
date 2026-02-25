"""
Task Models - 태스크 관련 데이터 모델 및 예외

태스크의 핵심 데이터 구조를 정의합니다.
"""

import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class TaskStatus(str, Enum):
    """태스크 상태"""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class TaskConflictError(Exception):
    """태스크 충돌 오류 (같은 키로 running 태스크 존재)"""
    pass


class TaskNotFoundError(Exception):
    """태스크 없음 오류"""
    pass


class TaskNotRunningError(Exception):
    """태스크가 running 상태가 아님"""
    pass


def utc_now() -> datetime:
    """현재 UTC 시간 반환"""
    return datetime.now(timezone.utc)


def datetime_to_str(dt: datetime) -> str:
    """datetime을 ISO 문자열로 변환"""
    return dt.isoformat()


def str_to_datetime(s: str) -> datetime:
    """ISO 문자열을 datetime으로 변환"""
    return datetime.fromisoformat(s)


@dataclass
class Task:
    """태스크 데이터"""
    client_id: str
    request_id: str
    prompt: str
    status: TaskStatus = TaskStatus.RUNNING

    # Claude Code 관련
    resume_session_id: Optional[str] = None
    claude_session_id: Optional[str] = None

    # 도구 설정 (런타임 전용, 영속화 안 됨)
    allowed_tools: Optional[List[str]] = field(default=None, repr=False)
    disallowed_tools: Optional[List[str]] = field(default=None, repr=False)
    use_mcp: bool = field(default=True, repr=False)

    # 결과
    result: Optional[str] = None
    error: Optional[str] = None
    result_delivered: bool = False

    # 타임스탬프
    created_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None

    # 런타임 전용 (영속화 안 됨)
    listeners: List[asyncio.Queue] = field(default_factory=list, repr=False)
    intervention_queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)
    execution_task: Optional[asyncio.Task] = field(default=None, repr=False)
    last_progress_text: Optional[str] = field(default=None, repr=False)

    @property
    def key(self) -> str:
        """태스크 키"""
        return f"{self.client_id}:{self.request_id}"

    def to_dict(self) -> dict:
        """영속화용 dict 변환"""
        return {
            "client_id": self.client_id,
            "request_id": self.request_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "resume_session_id": self.resume_session_id,
            "claude_session_id": self.claude_session_id,
            "result": self.result,
            "error": self.error,
            "result_delivered": self.result_delivered,
            "created_at": datetime_to_str(self.created_at),
            "completed_at": datetime_to_str(self.completed_at) if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """dict에서 복원"""
        return cls(
            client_id=data["client_id"],
            request_id=data["request_id"],
            prompt=data["prompt"],
            status=TaskStatus(data["status"]),
            resume_session_id=data.get("resume_session_id"),
            claude_session_id=data.get("claude_session_id"),
            result=data.get("result"),
            error=data.get("error"),
            result_delivered=data.get("result_delivered", False),
            created_at=str_to_datetime(data["created_at"]),
            completed_at=str_to_datetime(data["completed_at"]) if data.get("completed_at") else None,
        )
