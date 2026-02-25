"""session_id 기반 인터벤션 테스트

Phase 3: session_id 기반 인터벤션 API 검증
1. SessionEvent 모델 검증
2. TaskManager session_id 역방향 인덱스
3. session_id 기반 intervention 추가/조회
4. 인덱스 정리 (완료/에러/ack/cleanup 시)
"""

import asyncio

import pytest

from seosoyoung.soul.models.schemas import SessionEvent, SSEEventType
from seosoyoung.soul.service.task_manager import TaskManager, set_task_manager
from seosoyoung.soul.service.task_models import (
    TaskNotFoundError,
    TaskNotRunningError,
)


@pytest.fixture
def manager():
    """영속화 없는 TaskManager"""
    m = TaskManager(storage_path=None)
    yield m
    set_task_manager(None)


class TestSessionEventModel:
    """SessionEvent Pydantic 모델"""

    def test_session_event_type(self):
        event = SessionEvent(session_id="sess-abc123")
        assert event.type == "session"
        assert event.session_id == "sess-abc123"

    def test_session_event_model_dump(self):
        event = SessionEvent(session_id="sess-abc123")
        d = event.model_dump()
        assert d == {"type": "session", "session_id": "sess-abc123"}

    def test_sse_event_type_session(self):
        assert SSEEventType.SESSION == "session"
        assert SSEEventType.SESSION.value == "session"


class TestSessionIndex:
    """TaskManager session_id 역방향 인덱스"""

    async def test_register_and_lookup(self, manager):
        """session_id 등록 후 조회"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        task = manager.get_task_by_session("sess-abc")
        assert task is not None
        assert task.client_id == "bot"
        assert task.request_id == "req1"

    async def test_lookup_nonexistent(self, manager):
        """등록되지 않은 session_id 조회"""
        task = manager.get_task_by_session("nonexistent")
        assert task is None

    async def test_cleanup_on_complete(self, manager):
        """태스크 완료 시 session_id 인덱스 정리"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        await manager.complete_task("bot", "req1", "done")

        task = manager.get_task_by_session("sess-abc")
        assert task is None

    async def test_cleanup_on_error(self, manager):
        """태스크 에러 시 session_id 인덱스 정리"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        await manager.error_task("bot", "req1", "broke")

        task = manager.get_task_by_session("sess-abc")
        assert task is None

    async def test_cleanup_on_ack(self, manager):
        """태스크 ack 시 session_id 인덱스 정리"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")
        await manager.complete_task("bot", "req1", "done")

        await manager.ack_task("bot", "req1")

        task = manager.get_task_by_session("sess-abc")
        assert task is None

    async def test_multiple_sessions(self, manager):
        """여러 태스크에 각각 다른 session_id"""
        await manager.create_task("bot", "req1", "hello")
        await manager.create_task("bot", "req2", "world")

        manager.register_session("sess-1", "bot", "req1")
        manager.register_session("sess-2", "bot", "req2")

        t1 = manager.get_task_by_session("sess-1")
        t2 = manager.get_task_by_session("sess-2")

        assert t1.request_id == "req1"
        assert t2.request_id == "req2"


class TestInterventionBySession:
    """session_id 기반 개입 메시지"""

    async def test_add_intervention_by_session(self, manager):
        """session_id로 개입 메시지 추가"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        pos = await manager.add_intervention_by_session(
            "sess-abc", "새 질문", "user1"
        )
        assert pos == 1

        # 메시지 확인
        msg = await manager.get_intervention("bot", "req1")
        assert msg is not None
        assert msg["text"] == "새 질문"
        assert msg["user"] == "user1"

    async def test_add_intervention_session_not_found(self, manager):
        """존재하지 않는 session_id로 개입"""
        with pytest.raises(TaskNotFoundError):
            await manager.add_intervention_by_session(
                "nonexistent", "text", "user1"
            )

    async def test_add_intervention_session_not_running(self, manager):
        """완료된 태스크의 session_id로 개입 시도"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        # 완료 처리 시 인덱스 정리됨 → TaskNotFoundError
        await manager.complete_task("bot", "req1", "done")

        with pytest.raises(TaskNotFoundError):
            await manager.add_intervention_by_session(
                "sess-abc", "text", "user1"
            )

    async def test_multiple_interventions_by_session(self, manager):
        """session_id로 여러 개입 메시지"""
        await manager.create_task("bot", "req1", "hello")
        manager.register_session("sess-abc", "bot", "req1")

        await manager.add_intervention_by_session("sess-abc", "msg1", "user1")
        pos = await manager.add_intervention_by_session("sess-abc", "msg2", "user1")
        assert pos == 2

        msg1 = await manager.get_intervention("bot", "req1")
        msg2 = await manager.get_intervention("bot", "req1")
        assert msg1["text"] == "msg1"
        assert msg2["text"] == "msg2"
