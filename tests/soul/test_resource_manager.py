"""
test_resource_manager - 동시 실행 제한, 메모리 모니터링 테스트
"""

import asyncio

import pytest

from seosoyoung.soul.service.resource_manager import ResourceManager


@pytest.fixture
def rm():
    return ResourceManager(max_concurrent=2)


class TestResourceManagerProperties:
    def test_max_concurrent(self, rm):
        assert rm.max_concurrent == 2

    def test_initial_active_count(self, rm):
        assert rm.active_count == 0

    def test_initial_available_slots(self, rm):
        assert rm.available_slots == 2

    def test_can_acquire_initially(self, rm):
        assert rm.can_acquire() is True


class TestResourceManagerAcquire:
    async def test_acquire_increments_count(self, rm):
        async with rm.acquire():
            assert rm.active_count == 1
            assert rm.available_slots == 1
        assert rm.active_count == 0

    async def test_acquire_multiple(self, rm):
        async with rm.acquire():
            async with rm.acquire():
                assert rm.active_count == 2
                assert rm.available_slots == 0
                assert rm.can_acquire() is False

    async def test_acquire_timeout(self):
        rm = ResourceManager(max_concurrent=1)
        async with rm.acquire():
            # 이미 슬롯이 모두 사용 중이므로 타임아웃 발생
            with pytest.raises(RuntimeError, match="동시 실행 제한 초과"):
                async with rm.acquire(timeout=0.1):
                    pass

    async def test_acquire_releases_on_exception(self, rm):
        try:
            async with rm.acquire():
                raise ValueError("test error")
        except ValueError:
            pass

        # 예외 후에도 리소스가 해제되었는지 확인
        assert rm.active_count == 0
        assert rm.can_acquire() is True


class TestTryAcquire:
    def test_try_acquire_success(self, rm):
        assert rm.try_acquire() is True
        assert rm.active_count == 1

    def test_try_acquire_full(self):
        rm = ResourceManager(max_concurrent=1)
        assert rm.try_acquire() is True
        assert rm.try_acquire() is False

    def test_release_after_try_acquire(self):
        rm = ResourceManager(max_concurrent=1)
        rm.try_acquire()
        rm.release()
        assert rm.active_count == 0


class TestGetStats:
    def test_get_stats(self, rm):
        stats = rm.get_stats()
        assert "active_sessions" in stats
        assert "max_concurrent" in stats
        assert "available_slots" in stats
        # memory 키는 제거됨 (메모리 보고 코드 삭제)
        assert "memory" not in stats
