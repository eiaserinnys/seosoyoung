"""
TaskManager - 태스크 라이프사이클 관리

태스크 기반 아키텍처의 핵심 컴포넌트.
클라이언트(seosoyoung_bot 등)의 실행 요청을 태스크로 관리하고,
결과를 영속화하여 클라이언트 재시작 시에도 복구 가능하게 합니다.

이 모듈은 다음 서브모듈들을 조합합니다:
- task_models: 데이터 모델 및 예외
- task_storage: JSON 영속화
- task_listener: SSE 리스너 관리
- task_executor: 백그라운드 실행
"""

import asyncio
import logging
from datetime import timedelta
from pathlib import Path
from typing import Optional, Dict, List

# 서브모듈에서 import
from seosoyoung.soul.service.task_models import (
    Task,
    TaskStatus,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    utc_now,
)
from seosoyoung.soul.service.task_storage import TaskStorage
from seosoyoung.soul.service.task_listener import TaskListenerManager
from seosoyoung.soul.service.task_executor import TaskExecutor

# Re-export for backward compatibility
__all__ = [
    "Task",
    "TaskStatus",
    "TaskConflictError",
    "TaskNotFoundError",
    "TaskNotRunningError",
    "TaskManager",
    "task_manager",
    "get_task_manager",
    "init_task_manager",
    "set_task_manager",
    "utc_now",
]

logger = logging.getLogger(__name__)


class TaskManager:
    """
    태스크 라이프사이클 관리자

    역할:
    1. 태스크 생성/조회/삭제
    2. {client_id, request_id}로 활성 태스크 추적 (중복 방지)
    3. 태스크 상태 업데이트 및 결과 저장
    4. SSE 리스너 관리 (via TaskListenerManager)
    5. 개입 메시지 큐 관리
    6. JSON 파일 영속화 (via TaskStorage)
    7. 백그라운드 실행 (via TaskExecutor)
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Args:
            storage_path: 태스크 저장 파일 경로 (None이면 영속화 안 함)
        """
        # 핵심 데이터
        self._tasks: Dict[str, Task] = {}
        self._lock = asyncio.Lock()

        # 서브 컴포넌트들
        self._storage = TaskStorage(storage_path)
        self._listener_manager = TaskListenerManager(self._tasks)
        self._executor = TaskExecutor(
            tasks=self._tasks,
            listener_manager=self._listener_manager,
            get_intervention_func=self.get_intervention,
            complete_task_func=self._complete_task_internal,
            error_task_func=self._error_task_internal,
        )

    # === 로드/저장 ===

    async def load(self) -> int:
        """파일에서 태스크 로드"""
        return await self._storage.load(self._tasks)

    async def save(self) -> None:
        """태스크 상태 저장"""
        await self._storage.save(self._tasks)

    async def _schedule_save(self) -> None:
        """저장 예약 (debounce)"""
        await self._storage.schedule_save(self._tasks)

    # === CRUD 작업 ===

    def get_running_tasks(self) -> List[Task]:
        """실행 중인 태스크 목록 반환"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    async def create_task(
        self,
        client_id: str,
        request_id: str,
        prompt: str,
        resume_session_id: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        use_mcp: bool = True,
    ) -> Task:
        """
        새 태스크 생성

        Args:
            client_id: 클라이언트 ID (e.g., "seosoyoung_bot")
            request_id: 요청 ID (e.g., Slack thread ID)
            prompt: 실행할 프롬프트
            resume_session_id: 이전 세션 ID (대화 연속성용)
            allowed_tools: 허용 도구 목록 (None이면 제한 없음)
            disallowed_tools: 금지 도구 목록
            use_mcp: MCP 서버 연결 여부

        Returns:
            Task: 생성된 태스크

        Raises:
            TaskConflictError: 같은 키로 running 태스크가 존재
        """
        key = f"{client_id}:{request_id}"

        async with self._lock:
            existing = self._tasks.get(key)
            if existing:
                if existing.status == TaskStatus.RUNNING:
                    raise TaskConflictError(f"Task already running: {key}")
                logger.info(f"Overwriting existing task: {key}")

            task = Task(
                client_id=client_id,
                request_id=request_id,
                prompt=prompt,
                resume_session_id=resume_session_id,
                allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                use_mcp=use_mcp,
            )

            self._tasks[key] = task
            logger.info(f"Created task: {key}")

        await self._schedule_save()
        return task

    async def get_task(self, client_id: str, request_id: str) -> Optional[Task]:
        """태스크 조회"""
        key = f"{client_id}:{request_id}"
        return self._tasks.get(key)

    async def get_tasks_by_client(self, client_id: str) -> List[Task]:
        """클라이언트별 태스크 목록 조회"""
        return [
            task for task in self._tasks.values()
            if task.client_id == client_id
        ]

    async def _complete_task_internal(
        self,
        client_id: str,
        request_id: str,
        result: str,
        claude_session_id: Optional[str] = None,
    ) -> Optional[Task]:
        """태스크 완료 처리 (내부용 - executor에서 호출)"""
        return await self.complete_task(client_id, request_id, result, claude_session_id)

    async def complete_task(
        self,
        client_id: str,
        request_id: str,
        result: str,
        claude_session_id: Optional[str] = None,
    ) -> Optional[Task]:
        """
        태스크 완료 처리

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            result: 실행 결과
            claude_session_id: Claude Code 세션 ID

        Returns:
            업데이트된 태스크 (없으면 None)
        """
        key = f"{client_id}:{request_id}"

        async with self._lock:
            task = self._tasks.get(key)
            if not task:
                logger.warning(f"Task not found for complete: {key}")
                return None

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.claude_session_id = claude_session_id
            task.completed_at = utc_now()

            logger.info(f"Completed task: {key}")

        await self._schedule_save()
        return task

    async def _error_task_internal(
        self,
        client_id: str,
        request_id: str,
        error: str,
    ) -> Optional[Task]:
        """태스크 에러 처리 (내부용 - executor에서 호출)"""
        return await self.error_task(client_id, request_id, error)

    async def error_task(
        self,
        client_id: str,
        request_id: str,
        error: str,
    ) -> Optional[Task]:
        """
        태스크 에러 처리

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            error: 에러 메시지

        Returns:
            업데이트된 태스크 (없으면 None)
        """
        key = f"{client_id}:{request_id}"

        async with self._lock:
            task = self._tasks.get(key)
            if not task:
                logger.warning(f"Task not found for error: {key}")
                return None

            task.status = TaskStatus.ERROR
            task.error = error
            task.completed_at = utc_now()

            logger.info(f"Error task: {key} - {error}")

        await self._schedule_save()
        return task

    async def ack_task(self, client_id: str, request_id: str) -> bool:
        """
        결과 수신 확인 (태스크 삭제)

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID

        Returns:
            성공 여부
        """
        key = f"{client_id}:{request_id}"

        async with self._lock:
            task = self._tasks.pop(key, None)
            if not task:
                logger.warning(f"Task not found for ack: {key}")
                return False

            # intervention_queue 정리 (메모리 릭 방지)
            self._clear_queue(task.intervention_queue)
            # listeners 정리
            task.listeners.clear()

            logger.info(f"Acked task: {key}")

        await self._schedule_save()
        return True

    async def mark_delivered(self, client_id: str, request_id: str) -> bool:
        """
        결과 전달 완료 마킹

        ack 전에 결과가 전달되었음을 표시.
        서비스 재시작 시 이미 전달된 결과는 재전송하지 않음.

        Returns:
            성공 여부
        """
        key = f"{client_id}:{request_id}"

        async with self._lock:
            task = self._tasks.get(key)
            if not task:
                return False

            task.result_delivered = True

        await self._schedule_save()
        return True

    # === SSE 리스너 관리 (위임) ===

    async def add_listener(self, client_id: str, request_id: str, queue: asyncio.Queue) -> bool:
        """SSE 리스너 추가"""
        async with self._lock:
            return await self._listener_manager.add_listener(client_id, request_id, queue)

    async def remove_listener(self, client_id: str, request_id: str, queue: asyncio.Queue) -> None:
        """SSE 리스너 제거"""
        async with self._lock:
            await self._listener_manager.remove_listener(client_id, request_id, queue)

    async def broadcast(self, client_id: str, request_id: str, event: dict) -> int:
        """모든 리스너에게 이벤트 브로드캐스트"""
        return await self._listener_manager.broadcast(client_id, request_id, event)

    # === 개입 메시지 관리 ===

    async def add_intervention(
        self,
        client_id: str,
        request_id: str,
        text: str,
        user: str,
        attachment_paths: Optional[List[str]] = None,
    ) -> int:
        """
        개입 메시지 추가

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            text: 메시지 텍스트
            user: 사용자
            attachment_paths: 첨부 파일 경로

        Returns:
            큐 내 위치 (queue position)

        Raises:
            TaskNotFoundError: 태스크 없음
            TaskNotRunningError: 태스크가 running 상태가 아님
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)

        if not task:
            raise TaskNotFoundError(f"Task not found: {key}")

        if task.status != TaskStatus.RUNNING:
            raise TaskNotRunningError(f"Task is not running: {key}")

        message = {
            "text": text,
            "user": user,
            "attachment_paths": attachment_paths or [],
        }
        await task.intervention_queue.put(message)

        return task.intervention_queue.qsize()

    async def get_intervention(self, client_id: str, request_id: str) -> Optional[dict]:
        """
        개입 메시지 가져오기 (non-blocking)

        Returns:
            메시지 dict 또는 None
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if not task:
            return None

        try:
            return task.intervention_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    # === 백그라운드 실행 관리 (위임) ===

    async def start_execution(
        self,
        client_id: str,
        request_id: str,
        claude_runner,
        resource_manager,
    ) -> bool:
        """태스크의 Claude 실행을 백그라운드에서 시작"""
        return await self._executor.start_execution(
            client_id, request_id, claude_runner, resource_manager
        )

    def is_execution_running(self, client_id: str, request_id: str) -> bool:
        """태스크 실행이 진행 중인지 확인"""
        return self._executor.is_execution_running(client_id, request_id)

    async def send_reconnect_status(
        self,
        client_id: str,
        request_id: str,
        queue: asyncio.Queue
    ) -> None:
        """재연결 시 현재 상태 이벤트 전송"""
        await self._executor.send_reconnect_status(client_id, request_id, queue)

    # === 정리 ===

    async def cancel_running_tasks(self, timeout: float = 5.0) -> int:
        """실행 중인 모든 태스크 취소"""
        async with self._lock:
            return await self._executor.cancel_running_tasks(timeout)

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        오래된 태스크 정리

        Args:
            max_age_hours: 최대 보관 시간

        Returns:
            정리된 태스크 수
        """
        cutoff = utc_now() - timedelta(hours=max_age_hours)
        cleaned = 0

        async with self._lock:
            keys_to_remove = []
            for key, task in self._tasks.items():
                # RUNNING 상태 태스크 처리
                if task.status == TaskStatus.RUNNING:
                    # execution_task가 없거나 완료된 경우 (orphaned task)
                    if task.execution_task is None or task.execution_task.done():
                        if task.created_at < cutoff:
                            task.status = TaskStatus.ERROR
                            task.error = "실행 태스크 없이 오래된 running 상태 (orphaned)"
                            task.completed_at = utc_now()
                            keys_to_remove.append(key)
                            logger.warning(f"Cleaning up orphaned running task: {key}")
                    continue

                # 오래된 태스크 정리
                if task.created_at < cutoff:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                task = self._tasks[key]
                self._clear_queue(task.intervention_queue)
                task.listeners.clear()
                del self._tasks[key]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old tasks")
            await self._schedule_save()

        return cleaned

    def _clear_queue(self, queue: asyncio.Queue) -> None:
        """큐 내 모든 항목 제거"""
        try:
            while True:
                queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    def get_stats(self) -> dict:
        """통계 반환"""
        running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        error = sum(1 for t in self._tasks.values() if t.status == TaskStatus.ERROR)

        return {
            "total": len(self._tasks),
            "running": running,
            "completed": completed,
            "error": error,
        }


# 싱글톤 인스턴스는 main.py에서 초기화
task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """TaskManager 싱글톤 반환"""
    global task_manager
    if task_manager is None:
        raise RuntimeError("TaskManager not initialized. Call init_task_manager first.")
    return task_manager


def init_task_manager(storage_path: Optional[Path] = None) -> TaskManager:
    """TaskManager 초기화"""
    global task_manager
    task_manager = TaskManager(storage_path=storage_path)
    return task_manager


def set_task_manager(manager: Optional[TaskManager]) -> None:
    """TaskManager 인스턴스 설정 (테스트용)"""
    global task_manager
    task_manager = manager
