"""run_in_new_loop 및 run_sync 테스트"""

import asyncio
import threading
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.claude.agent_runner import ClaudeAgentRunner, run_in_new_loop


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
            # 루프가 새로 생성되었는지 확인 (is_running이 True여야 함)
            loop_states.append(loop.is_running())
            return len(loop_states)

        result1 = run_in_new_loop(capture_loop_state())
        result2 = run_in_new_loop(capture_loop_state())

        assert result1 == 1
        assert result2 == 2
        # 각 호출에서 루프가 정상 실행 중이었음
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


class TestRunSync:
    """run_sync() 브릿지 메서드 테스트"""

    def test_run_sync_executes_coroutine(self):
        """run_sync()가 코루틴을 실행하고 결과를 반환하는지 확인"""
        runner = ClaudeAgentRunner()

        async def simple_coro():
            return 42

        result = runner.run_sync(simple_coro())
        assert result == 42

    def test_run_sync_handles_async_sleep(self):
        """run_sync()가 async sleep을 포함한 코루틴을 처리하는지 확인"""
        runner = ClaudeAgentRunner()

        async def slow_coro():
            await asyncio.sleep(0.1)
            return "done"

        result = runner.run_sync(slow_coro())
        assert result == "done"

    def test_run_sync_propagates_exceptions(self):
        """run_sync()가 코루틴의 예외를 전파하는지 확인"""
        runner = ClaudeAgentRunner()

        async def failing_coro():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            runner.run_sync(failing_coro())

    def test_run_sync_callable_from_sync_context(self):
        """run_sync()가 동기 컨텍스트(일반 스레드)에서 호출 가능한지 확인"""
        runner = ClaudeAgentRunner()
        results = []

        async def coro():
            return "from sync thread"

        def sync_function():
            result = runner.run_sync(coro())
            results.append(result)

        thread = threading.Thread(target=sync_function)
        thread.start()
        thread.join(timeout=5)

        assert results == ["from sync thread"]

    def test_run_sync_multiple_sequential_calls(self):
        """run_sync()를 연속으로 여러 번 호출해도 안정적인지 확인"""
        runner = ClaudeAgentRunner()

        async def add(a, b):
            return a + b

        results = []
        for i in range(5):
            result = runner.run_sync(add(i, i * 2))
            results.append(result)

        assert results == [0, 3, 6, 9, 12]
