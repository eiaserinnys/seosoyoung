"""run_in_new_loop 테스트"""

import asyncio
import threading
import pytest
from pathlib import Path

from seosoyoung.utils.async_bridge import run_in_new_loop


class TestRunInNewLoop:
    """run_in_new_loop() 유틸리티 함수 테스트"""

    def test_basic_coroutine(self):
        """기본 코루틴 실행 및 결과 반환"""
        async def simple_coro():
            return 42

        result = run_in_new_loop(simple_coro())
        assert result == 42

    def test_async_sleep(self):
        """async sleep을 포함한 코루틴 처리"""
        async def slow_coro():
            await asyncio.sleep(0.05)
            return "done"

        result = run_in_new_loop(slow_coro())
        assert result == "done"

    def test_propagates_exceptions(self):
        """코루틴의 예외를 전파"""
        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_in_new_loop(failing_coro())

    def test_sequential_calls_isolated(self):
        """순차 호출이 격리된 루프에서 실행되는지 확인 (anyio 잔여물 격리)"""
        loop_states = []

        async def capture_loop_state():
            loop = asyncio.get_running_loop()
            loop_states.append(loop.is_running())
            return len(loop_states)

        result1 = run_in_new_loop(capture_loop_state())
        result2 = run_in_new_loop(capture_loop_state())

        assert result1 == 1
        assert result2 == 2
        assert all(loop_states)

    def test_callable_from_sync_thread(self):
        """동기 스레드에서 호출 가능한지 확인"""
        results = []

        async def coro():
            return "from sync thread"

        def sync_function():
            result = run_in_new_loop(coro())
            results.append(result)

        thread = threading.Thread(target=sync_function)
        thread.start()
        thread.join(timeout=5)

        assert results == ["from sync thread"]

    def test_multiple_sequential_calls(self):
        """연속 호출이 안정적인지 확인 (핵심 버그 재현 검증)"""
        async def add(a, b):
            return a + b

        results = []
        for i in range(5):
            result = run_in_new_loop(add(i, i * 2))
            results.append(result)

        assert results == [0, 3, 6, 9, 12]
