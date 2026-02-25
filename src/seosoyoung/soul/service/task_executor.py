"""
Task Executor - 백그라운드 태스크 실행 관리

Claude Code 실행을 백그라운드에서 관리합니다.
"""

import asyncio
import logging
from typing import Dict, Callable, Awaitable, Optional, TYPE_CHECKING

from seosoyoung.soul.service.task_models import Task, TaskStatus

if TYPE_CHECKING:
    from seosoyoung.soul.service.task_listener import TaskListenerManager

logger = logging.getLogger(__name__)


class TaskExecutor:
    """
    백그라운드 태스크 실행 관리자

    Claude Code 실행을 백그라운드에서 관리하고,
    실행 결과를 리스너에게 브로드캐스트합니다.
    """

    def __init__(
        self,
        tasks: Dict[str, Task],
        listener_manager: "TaskListenerManager",
        get_intervention_func: Callable[[str, str], Awaitable[Optional[dict]]],
        complete_task_func: Callable[[str, str, str, Optional[str]], Awaitable[Optional[Task]]],
        error_task_func: Callable[[str, str, str], Awaitable[Optional[Task]]],
        register_session_func: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        Args:
            tasks: TaskManager의 태스크 딕셔너리 참조
            listener_manager: 리스너 매니저
            get_intervention_func: 개입 메시지 가져오기 함수
            complete_task_func: 태스크 완료 처리 함수
            error_task_func: 태스크 에러 처리 함수
            register_session_func: session_id 등록 함수 (session_id, client_id, request_id)
        """
        self._tasks = tasks
        self._listener_manager = listener_manager
        self._get_intervention = get_intervention_func
        self._complete_task = complete_task_func
        self._error_task = error_task_func
        self._register_session = register_session_func

    async def start_execution(
        self,
        client_id: str,
        request_id: str,
        claude_runner,
        resource_manager,
    ) -> bool:
        """
        태스크의 Claude 실행을 백그라운드에서 시작

        SSE 연결과 독립적으로 실행되어, 클라이언트 재연결 시에도
        실행이 계속됩니다.

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            claude_runner: SoulEngineAdapter 인스턴스 (execute() 메서드 제공)
            resource_manager: ResourceManager 인스턴스

        Returns:
            bool: 성공 여부
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if not task:
            logger.warning(f"Task not found for execution: {key}")
            return False

        if task.execution_task is not None:
            logger.warning(f"Task already executing: {key}")
            return False

        # 백그라운드 태스크 생성
        task.execution_task = asyncio.create_task(
            self._run_execution(
                task=task,
                claude_runner=claude_runner,
                resource_manager=resource_manager,
            )
        )
        logger.info(f"Started background execution for task: {key}")

        return True

    async def _run_execution(
        self,
        task: Task,
        claude_runner,
        resource_manager,
    ) -> None:
        """백그라운드에서 Claude 실행 및 이벤트 브로드캐스트"""
        key = task.key

        try:
            async with resource_manager.acquire(timeout=5.0):
                # 개입 메시지 가져오기 함수
                async def get_intervention():
                    return await self._get_intervention(task.client_id, task.request_id)

                # 개입 메시지 전송 콜백
                async def on_intervention_sent(user: str, text: str):
                    event = {"type": "intervention_sent", "user": user, "text": text}
                    await self._listener_manager.broadcast(task.client_id, task.request_id, event)

                # Claude Code 실행 (요청별 도구 설정 전달)
                async for event in claude_runner.execute(
                    prompt=task.prompt,
                    resume_session_id=task.resume_session_id,
                    get_intervention=get_intervention,
                    on_intervention_sent=on_intervention_sent,
                    allowed_tools=task.allowed_tools,
                    disallowed_tools=task.disallowed_tools,
                    use_mcp=task.use_mcp,
                ):
                    event_dict = event.model_dump()

                    # session_id 등록 (인터벤션 역인덱스)
                    if event.type == "session" and self._register_session:
                        self._register_session(
                            event_dict.get("session_id", ""),
                            task.client_id,
                            task.request_id,
                        )

                    # 진행 상황 저장 (재연결용)
                    if event.type == "progress":
                        task.last_progress_text = event_dict.get("text", "")

                    # 리스너들에게 브로드캐스트
                    await self._listener_manager.broadcast(
                        task.client_id, task.request_id, event_dict
                    )

                    # 완료 또는 오류 시 태스크 상태 업데이트
                    if event.type == "complete":
                        await self._complete_task(
                            task.client_id,
                            task.request_id,
                            event.result,
                            event.claude_session_id,
                        )
                    elif event.type == "error":
                        await self._error_task(
                            task.client_id,
                            task.request_id,
                            event.message,
                        )

        except RuntimeError as e:
            # 리소스 획득 실패
            error_msg = str(e)
            logger.error(f"Resource acquisition failed for task {key}: {error_msg}")
            await self._error_task(task.client_id, task.request_id, error_msg)
            # 에러 이벤트 브로드캐스트
            await self._listener_manager.broadcast(
                task.client_id, task.request_id,
                {"type": "error", "message": error_msg}
            )

        except asyncio.CancelledError:
            logger.info(f"Task execution cancelled: {key}")
            raise

        except Exception as e:
            logger.exception(f"Task execution error for {key}: {e}")
            error_msg = f"실행 오류: {str(e)}"
            await self._error_task(task.client_id, task.request_id, error_msg)
            # 에러 이벤트 브로드캐스트
            await self._listener_manager.broadcast(
                task.client_id, task.request_id,
                {"type": "error", "message": error_msg}
            )

        finally:
            task.execution_task = None
            logger.info(f"Background execution finished for task: {key}")

    def is_execution_running(self, client_id: str, request_id: str) -> bool:
        """태스크 실행이 진행 중인지 확인"""
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        return task is not None and task.execution_task is not None

    async def send_reconnect_status(
        self,
        client_id: str,
        request_id: str,
        queue: asyncio.Queue
    ) -> None:
        """
        재연결 시 현재 상태 이벤트 전송

        새로 연결된 리스너에게 현재 태스크 상태를 알려줍니다.
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if not task:
            return

        # 재연결 알림 이벤트
        reconnect_event = {
            "type": "reconnected",
            "status": task.status.value,
            "has_execution": task.execution_task is not None,
        }

        # 마지막 진행 상황이 있으면 포함
        if task.last_progress_text:
            reconnect_event["last_progress"] = task.last_progress_text

        try:
            await queue.put(reconnect_event)
            logger.debug(f"Sent reconnect status to listener for task {key}")

        except Exception as e:
            logger.warning(f"Failed to send reconnect status: {e}")

    async def cancel_running_tasks(self, timeout: float = 5.0) -> int:
        """
        실행 중인 모든 태스크 취소

        서비스 shutdown 시 호출하여 고아 프로세스 방지.

        Args:
            timeout: 취소 대기 시간 (초)

        Returns:
            취소된 태스크 수
        """
        tasks_to_cancel = []

        for key, task in self._tasks.items():
            if task.execution_task and not task.execution_task.done():
                task.execution_task.cancel()
                tasks_to_cancel.append((key, task.execution_task))
                logger.info(f"Cancelling execution for task: {key}")

        if not tasks_to_cancel:
            return 0

        # 모든 취소된 태스크 완료 대기 (gather로 병렬 대기)
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[t for _, t in tasks_to_cancel],
                    return_exceptions=True
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Task cancellation timeout after {timeout}s")

        # 취소된 태스크 수 카운트
        cancelled_count = sum(1 for _, t in tasks_to_cancel if t.done())
        logger.info(f"Cancelled {cancelled_count}/{len(tasks_to_cancel)} running tasks")
        return cancelled_count
