"""
Task Storage - 태스크 영속화 관리

JSON 파일 기반의 태스크 상태 영속화를 담당합니다.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from seosoyoung.mcp.soul.service.task_models import (
    Task,
    TaskStatus,
    utc_now,
    datetime_to_str,
)

logger = logging.getLogger(__name__)


class TaskStorage:
    """
    태스크 영속화 관리자

    JSON 파일을 통해 태스크 상태를 영속화합니다.
    - debounce 저장으로 I/O 최적화
    - atomic write로 데이터 무결성 보장
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Args:
            storage_path: 태스크 저장 파일 경로 (None이면 영속화 안 함)
        """
        self._storage_path = storage_path
        self._save_scheduled = False

    async def load(self, tasks: Dict[str, Task]) -> int:
        """
        파일에서 태스크 로드

        서비스 시작 시 호출. running 상태의 태스크는 error로 마킹.

        Args:
            tasks: 로드된 태스크를 저장할 딕셔너리

        Returns:
            로드된 태스크 수
        """
        if not self._storage_path or not self._storage_path.exists():
            logger.info("No existing tasks file to load")
            return 0

        try:
            data = json.loads(self._storage_path.read_text())
            tasks_data = data.get("tasks", {})

            loaded = 0
            for key, task_data in tasks_data.items():
                try:
                    task = Task.from_dict(task_data)

                    # running 상태의 태스크는 서비스 재시작으로 중단된 것
                    if task.status == TaskStatus.RUNNING:
                        task.status = TaskStatus.ERROR
                        task.error = "서비스 재시작으로 중단됨"
                        task.completed_at = utc_now()
                        logger.warning(f"Marked interrupted task as error: {key}")

                    tasks[key] = task
                    loaded += 1
                except Exception as e:
                    logger.error(f"Failed to load task {key}: {e}")

            logger.info(f"Loaded {loaded} tasks from storage")

            # running → error 변경사항 저장
            await self._save(tasks)

            return loaded

        except Exception as e:
            logger.error(f"Failed to load tasks file: {e}")
            return 0

    async def _save(self, tasks: Dict[str, Task]) -> None:
        """태스크를 파일에 저장 (내부용)"""
        if not self._storage_path:
            return

        try:
            data = {
                "tasks": {key: task.to_dict() for key, task in tasks.items()},
                "last_saved": datetime_to_str(utc_now()),
            }

            # 디렉토리 생성
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            # 임시 파일에 먼저 쓰고 rename (atomic write)
            temp_path = self._storage_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            temp_path.rename(self._storage_path)

            logger.debug(f"Saved {len(tasks)} tasks to storage")

        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")

    async def save(self, tasks: Dict[str, Task]) -> None:
        """태스크 상태 저장 (public interface)"""
        await self._save(tasks)

    async def schedule_save(self, tasks: Dict[str, Task]) -> None:
        """저장 예약 (debounce)"""
        if self._save_scheduled:
            return

        self._save_scheduled = True

        async def do_save():
            await asyncio.sleep(0.5)  # 500ms debounce
            self._save_scheduled = False
            await self._save(tasks)

        asyncio.create_task(do_save())
