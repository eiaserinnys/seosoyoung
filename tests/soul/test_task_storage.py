"""
test_task_storage - 로드/저장, atomic write, running→error 복구 테스트
"""

import json
from pathlib import Path

import pytest

from seosoyoung.mcp.soul.service.task_models import Task, TaskStatus, utc_now, datetime_to_str
from seosoyoung.mcp.soul.service.task_storage import TaskStorage


@pytest.fixture
def tmp_storage_path(tmp_path):
    return tmp_path / "data" / "tasks.json"


@pytest.fixture
def storage(tmp_storage_path):
    return TaskStorage(tmp_storage_path)


class TestTaskStorageSave:
    async def test_save_creates_file(self, storage, tmp_storage_path):
        tasks = {
            "bot:req1": Task(client_id="bot", request_id="req1", prompt="hello")
        }
        await storage.save(tasks)
        assert tmp_storage_path.exists()

    async def test_save_creates_directories(self, storage, tmp_storage_path):
        tasks = {"bot:req1": Task(client_id="bot", request_id="req1", prompt="hello")}
        await storage.save(tasks)
        assert tmp_storage_path.parent.exists()

    async def test_save_valid_json(self, storage, tmp_storage_path):
        tasks = {"bot:req1": Task(client_id="bot", request_id="req1", prompt="hello")}
        await storage.save(tasks)

        data = json.loads(tmp_storage_path.read_text())
        assert "tasks" in data
        assert "last_saved" in data
        assert "bot:req1" in data["tasks"]

    async def test_save_multiple_tasks(self, storage, tmp_storage_path):
        tasks = {
            "bot:req1": Task(client_id="bot", request_id="req1", prompt="hello"),
            "bot:req2": Task(client_id="bot", request_id="req2", prompt="world"),
        }
        await storage.save(tasks)

        data = json.loads(tmp_storage_path.read_text())
        assert len(data["tasks"]) == 2

    async def test_save_empty_tasks(self, storage, tmp_storage_path):
        await storage.save({})
        data = json.loads(tmp_storage_path.read_text())
        assert len(data["tasks"]) == 0


class TestTaskStorageLoad:
    async def test_load_nonexistent_file(self, storage):
        tasks = {}
        loaded = await storage.load(tasks)
        assert loaded == 0
        assert len(tasks) == 0

    async def test_load_from_saved(self, storage, tmp_storage_path):
        # 먼저 저장
        original_tasks = {
            "bot:req1": Task(client_id="bot", request_id="req1", prompt="hello"),
        }
        original_tasks["bot:req1"].status = TaskStatus.COMPLETED
        original_tasks["bot:req1"].result = "done"
        original_tasks["bot:req1"].completed_at = utc_now()
        await storage.save(original_tasks)

        # 로드
        loaded_tasks = {}
        loaded = await storage.load(loaded_tasks)
        assert loaded == 1
        assert "bot:req1" in loaded_tasks
        assert loaded_tasks["bot:req1"].status == TaskStatus.COMPLETED
        assert loaded_tasks["bot:req1"].result == "done"

    async def test_load_marks_running_as_error(self, storage, tmp_storage_path):
        """running 상태의 태스크는 서비스 재시작으로 중단된 것으로 간주"""
        now = utc_now()
        data = {
            "tasks": {
                "bot:req1": {
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
            },
            "last_saved": datetime_to_str(now),
        }

        tmp_storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_storage_path.write_text(json.dumps(data))

        tasks = {}
        loaded = await storage.load(tasks)
        assert loaded == 1
        task = tasks["bot:req1"]
        assert task.status == TaskStatus.ERROR
        assert task.error == "서비스 재시작으로 중단됨"
        assert task.completed_at is not None

    async def test_load_preserves_completed_tasks(self, storage, tmp_storage_path):
        """completed 태스크는 그대로 유지"""
        now = utc_now()
        data = {
            "tasks": {
                "bot:req1": {
                    "client_id": "bot",
                    "request_id": "req1",
                    "prompt": "hello",
                    "status": "completed",
                    "resume_session_id": None,
                    "claude_session_id": "sess-1",
                    "result": "result text",
                    "error": None,
                    "result_delivered": False,
                    "created_at": datetime_to_str(now),
                    "completed_at": datetime_to_str(now),
                }
            },
            "last_saved": datetime_to_str(now),
        }

        tmp_storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_storage_path.write_text(json.dumps(data))

        tasks = {}
        loaded = await storage.load(tasks)
        assert loaded == 1
        assert tasks["bot:req1"].status == TaskStatus.COMPLETED
        assert tasks["bot:req1"].result == "result text"

    async def test_load_corrupted_data(self, tmp_storage_path):
        """손상된 데이터는 건너뛰고 로드"""
        tmp_storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_storage_path.write_text("not json")

        storage = TaskStorage(tmp_storage_path)
        tasks = {}
        loaded = await storage.load(tasks)
        assert loaded == 0


class TestTaskStorageNoPersistence:
    async def test_none_path_skips_save(self):
        storage = TaskStorage(storage_path=None)
        tasks = {"bot:req1": Task(client_id="bot", request_id="req1", prompt="hello")}
        # save가 에러 없이 조용히 스킵되는지 확인
        await storage.save(tasks)

    async def test_none_path_skips_load(self):
        storage = TaskStorage(storage_path=None)
        tasks = {}
        loaded = await storage.load(tasks)
        assert loaded == 0
