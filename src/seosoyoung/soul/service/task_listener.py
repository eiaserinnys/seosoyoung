"""
Task Listener - SSE 리스너 관리

SSE 연결을 통한 이벤트 브로드캐스트를 담당합니다.
"""

import asyncio
import logging
from typing import Dict

from seosoyoung.soul.service.task_models import Task

logger = logging.getLogger(__name__)


class TaskListenerManager:
    """
    SSE 리스너 관리자

    태스크별 리스너 큐를 관리하고 이벤트를 브로드캐스트합니다.
    """

    def __init__(self, tasks: Dict[str, Task]):
        """
        Args:
            tasks: TaskManager의 태스크 딕셔너리 참조
        """
        self._tasks = tasks

    async def add_listener(self, client_id: str, request_id: str, queue: asyncio.Queue) -> bool:
        """
        SSE 리스너 추가

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            queue: 이벤트를 받을 큐

        Returns:
            성공 여부 (태스크 존재 여부)
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if not task:
            return False

        task.listeners.append(queue)
        logger.info(f"[LISTENER] Added listener to task {key}, total: {len(task.listeners)}")
        return True

    async def remove_listener(self, client_id: str, request_id: str, queue: asyncio.Queue) -> None:
        """
        SSE 리스너 제거

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            queue: 제거할 큐
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if task and queue in task.listeners:
            task.listeners.remove(queue)
            logger.info(f"[LISTENER] Removed listener from task {key}, remaining: {len(task.listeners)}")

    async def broadcast(self, client_id: str, request_id: str, event: dict) -> int:
        """
        모든 리스너에게 이벤트 브로드캐스트

        Args:
            client_id: 클라이언트 ID
            request_id: 요청 ID
            event: 브로드캐스트할 이벤트

        Returns:
            전송된 리스너 수
        """
        key = f"{client_id}:{request_id}"
        task = self._tasks.get(key)
        if not task:
            return 0

        count = 0
        for queue in task.listeners:
            try:
                await queue.put(event)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to listener: {e}")

        if count > 0:
            event_type = event.get("type", "unknown")
            logger.info(f"[BROADCAST] {key} -> {count} listener(s), event={event_type}")

        return count
