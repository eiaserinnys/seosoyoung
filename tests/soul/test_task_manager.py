"""
test_task_manager - CRUD, 충돌 감지, ack, cleanup 테스트
"""

import asyncio
from datetime import timedelta

import pytest

from seosoyoung.soul.service.task_manager import TaskManager, set_task_manager
from seosoyoung.soul.service.task_models import (
    Task,
    TaskStatus,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    utc_now,
)


@pytest.fixture
def manager():
    """영속화 없는 TaskManager"""
    m = TaskManager(storage_path=None)
    yield m
    set_task_manager(None)


class TestCreateTask:
    async def test_create_basic(self, manager):
        task = await manager.create_task("bot", "req1", "hello")
        assert task.client_id == "bot"
        assert task.request_id == "req1"
        assert task.prompt == "hello"
        assert task.status == TaskStatus.RUNNING

    async def test_create_with_resume(self, manager):
        task = await manager.create_task("bot", "req1", "hello", resume_session_id="sess-1")
        assert task.resume_session_id == "sess-1"

    async def test_create_conflict_running(self, manager):
        await manager.create_task("bot", "req1", "hello")
        with pytest.raises(TaskConflictError):
            await manager.create_task("bot", "req1", "hello again")

    async def test_create_overwrites_completed(self, manager):
        task1 = await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "done")

        task2 = await manager.create_task("bot", "req1", "new prompt")
        assert task2.prompt == "new prompt"
        assert task2.status == TaskStatus.RUNNING


class TestGetTask:
    async def test_get_existing(self, manager):
        await manager.create_task("bot", "req1", "hello")
        task = await manager.get_task("bot", "req1")
        assert task is not None
        assert task.prompt == "hello"

    async def test_get_nonexistent(self, manager):
        task = await manager.get_task("bot", "nonexistent")
        assert task is None

    async def test_get_tasks_by_client(self, manager):
        await manager.create_task("bot1", "req1", "hello")
        await manager.create_task("bot1", "req2", "world")
        await manager.create_task("bot2", "req1", "other")

        bot1_tasks = await manager.get_tasks_by_client("bot1")
        assert len(bot1_tasks) == 2

        bot2_tasks = await manager.get_tasks_by_client("bot2")
        assert len(bot2_tasks) == 1

    async def test_get_running_tasks(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.create_task("bot", "req2", "world")
        await manager.complete_task("bot", "req1", "done")

        running = manager.get_running_tasks()
        assert len(running) == 1
        assert running[0].request_id == "req2"


class TestCompleteTask:
    async def test_complete_basic(self, manager):
        await manager.create_task("bot", "req1", "hello")
        task = await manager.complete_task("bot", "req1", "result")

        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.result == "result"
        assert task.completed_at is not None

    async def test_complete_with_session_id(self, manager):
        await manager.create_task("bot", "req1", "hello")
        task = await manager.complete_task("bot", "req1", "result", claude_session_id="sess-1")
        assert task.claude_session_id == "sess-1"

    async def test_complete_nonexistent(self, manager):
        task = await manager.complete_task("bot", "nonexistent", "result")
        assert task is None


class TestErrorTask:
    async def test_error_basic(self, manager):
        await manager.create_task("bot", "req1", "hello")
        task = await manager.error_task("bot", "req1", "something broke")

        assert task is not None
        assert task.status == TaskStatus.ERROR
        assert task.error == "something broke"
        assert task.completed_at is not None

    async def test_error_nonexistent(self, manager):
        task = await manager.error_task("bot", "nonexistent", "error")
        assert task is None


class TestAckTask:
    async def test_ack_removes_task(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "result")

        success = await manager.ack_task("bot", "req1")
        assert success is True

        task = await manager.get_task("bot", "req1")
        assert task is None

    async def test_ack_nonexistent(self, manager):
        success = await manager.ack_task("bot", "nonexistent")
        assert success is False


class TestMarkDelivered:
    async def test_mark_delivered(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "result")

        success = await manager.mark_delivered("bot", "req1")
        assert success is True

        task = await manager.get_task("bot", "req1")
        assert task.result_delivered is True

    async def test_mark_delivered_nonexistent(self, manager):
        success = await manager.mark_delivered("bot", "nonexistent")
        assert success is False


class TestIntervention:
    async def test_add_intervention(self, manager):
        await manager.create_task("bot", "req1", "hello")
        pos = await manager.add_intervention("bot", "req1", "stop", "user1")
        assert pos == 1

    async def test_add_intervention_not_found(self, manager):
        with pytest.raises(TaskNotFoundError):
            await manager.add_intervention("bot", "nonexistent", "stop", "user1")

    async def test_add_intervention_not_running(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "done")

        with pytest.raises(TaskNotRunningError):
            await manager.add_intervention("bot", "req1", "stop", "user1")

    async def test_get_intervention(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.add_intervention("bot", "req1", "stop", "user1")

        msg = await manager.get_intervention("bot", "req1")
        assert msg is not None
        assert msg["text"] == "stop"
        assert msg["user"] == "user1"

    async def test_get_intervention_empty(self, manager):
        await manager.create_task("bot", "req1", "hello")
        msg = await manager.get_intervention("bot", "req1")
        assert msg is None


class TestCleanup:
    async def test_cleanup_old_completed_tasks(self, manager):
        task = await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "result")

        # created_at을 과거로 조작
        task_ref = await manager.get_task("bot", "req1")
        task_ref.created_at = utc_now() - timedelta(hours=25)

        cleaned = await manager.cleanup_old_tasks(max_age_hours=24)
        assert cleaned == 1

        task = await manager.get_task("bot", "req1")
        assert task is None

    async def test_cleanup_preserves_recent_tasks(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.complete_task("bot", "req1", "result")

        cleaned = await manager.cleanup_old_tasks(max_age_hours=24)
        assert cleaned == 0

        task = await manager.get_task("bot", "req1")
        assert task is not None


class TestStats:
    async def test_stats(self, manager):
        await manager.create_task("bot", "req1", "hello")
        await manager.create_task("bot", "req2", "world")
        await manager.complete_task("bot", "req1", "done")

        stats = manager.get_stats()
        assert stats["total"] == 2
        assert stats["running"] == 1
        assert stats["completed"] == 1
        assert stats["error"] == 0
