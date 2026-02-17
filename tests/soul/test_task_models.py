"""
test_task_models - Task 생성, 상태 전이, 직렬화/역직렬화 테스트
"""

import asyncio
from datetime import datetime, timezone

from seosoyoung.mcp.soul.service.task_models import (
    Task,
    TaskStatus,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    utc_now,
    datetime_to_str,
    str_to_datetime,
)


class TestTaskCreation:
    def test_create_task_defaults(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        assert task.client_id == "bot"
        assert task.request_id == "req1"
        assert task.prompt == "hello"
        assert task.status == TaskStatus.RUNNING
        assert task.result is None
        assert task.error is None
        assert task.result_delivered is False
        assert task.resume_session_id is None
        assert task.claude_session_id is None
        assert task.completed_at is None

    def test_task_key(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        assert task.key == "bot:req1"

    def test_task_with_resume_session(self):
        task = Task(
            client_id="bot",
            request_id="req1",
            prompt="hello",
            resume_session_id="abc-123",
        )
        assert task.resume_session_id == "abc-123"

    def test_task_runtime_fields_initialized(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        assert isinstance(task.listeners, list)
        assert len(task.listeners) == 0
        assert isinstance(task.intervention_queue, asyncio.Queue)
        assert task.execution_task is None
        assert task.last_progress_text is None


class TestTaskStatusTransitions:
    def test_complete_task(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        assert task.status == TaskStatus.RUNNING

        task.status = TaskStatus.COMPLETED
        task.result = "done"
        task.completed_at = utc_now()

        assert task.status == TaskStatus.COMPLETED
        assert task.result == "done"
        assert task.completed_at is not None

    def test_error_task(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        task.status = TaskStatus.ERROR
        task.error = "something went wrong"
        task.completed_at = utc_now()

        assert task.status == TaskStatus.ERROR
        assert task.error == "something went wrong"

    def test_mark_delivered(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        assert task.result_delivered is False
        task.result_delivered = True
        assert task.result_delivered is True


class TestTaskSerialization:
    def test_to_dict(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        d = task.to_dict()

        assert d["client_id"] == "bot"
        assert d["request_id"] == "req1"
        assert d["prompt"] == "hello"
        assert d["status"] == "running"
        assert d["result"] is None
        assert d["error"] is None
        assert d["result_delivered"] is False
        assert "created_at" in d
        assert d["completed_at"] is None

    def test_to_dict_completed(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        task.status = TaskStatus.COMPLETED
        task.result = "result text"
        task.claude_session_id = "session-123"
        task.completed_at = utc_now()

        d = task.to_dict()
        assert d["status"] == "completed"
        assert d["result"] == "result text"
        assert d["claude_session_id"] == "session-123"
        assert d["completed_at"] is not None

    def test_from_dict(self):
        now = utc_now()
        d = {
            "client_id": "bot",
            "request_id": "req1",
            "prompt": "hello",
            "status": "running",
            "resume_session_id": None,
            "claude_session_id": None,
            "result": None,
            "error": None,
            "result_delivered": False,
            "created_at": datetime_to_str(now),
            "completed_at": None,
        }

        task = Task.from_dict(d)
        assert task.client_id == "bot"
        assert task.request_id == "req1"
        assert task.status == TaskStatus.RUNNING
        assert task.result is None

    def test_roundtrip(self):
        task = Task(
            client_id="bot",
            request_id="req1",
            prompt="hello",
            resume_session_id="session-abc",
        )
        task.status = TaskStatus.COMPLETED
        task.result = "result"
        task.claude_session_id = "session-xyz"
        task.result_delivered = True
        task.completed_at = utc_now()

        d = task.to_dict()
        restored = Task.from_dict(d)

        assert restored.client_id == task.client_id
        assert restored.request_id == task.request_id
        assert restored.prompt == task.prompt
        assert restored.status == task.status
        assert restored.result == task.result
        assert restored.claude_session_id == task.claude_session_id
        assert restored.result_delivered == task.result_delivered
        assert restored.resume_session_id == task.resume_session_id

    def test_runtime_fields_not_serialized(self):
        task = Task(client_id="bot", request_id="req1", prompt="hello")
        d = task.to_dict()
        assert "listeners" not in d
        assert "intervention_queue" not in d
        assert "execution_task" not in d
        assert "last_progress_text" not in d


class TestDatetimeHelpers:
    def test_utc_now(self):
        now = utc_now()
        assert isinstance(now, datetime)
        assert now.tzinfo == timezone.utc

    def test_datetime_roundtrip(self):
        now = utc_now()
        s = datetime_to_str(now)
        restored = str_to_datetime(s)
        assert restored == now


class TestExceptions:
    def test_task_conflict_error(self):
        err = TaskConflictError("conflict")
        assert str(err) == "conflict"

    def test_task_not_found_error(self):
        err = TaskNotFoundError("not found")
        assert str(err) == "not found"

    def test_task_not_running_error(self):
        err = TaskNotRunningError("not running")
        assert str(err) == "not running"


class TestTaskStatusEnum:
    def test_values(self):
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.ERROR.value == "error"

    def test_from_string(self):
        assert TaskStatus("running") == TaskStatus.RUNNING
        assert TaskStatus("completed") == TaskStatus.COMPLETED
        assert TaskStatus("error") == TaskStatus.ERROR
