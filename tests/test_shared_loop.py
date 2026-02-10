"""공유 이벤트 루프 및 run_sync 테스트"""

import asyncio
import threading
import time
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.claude.agent_runner import ClaudeAgentRunner


class TestSharedLoop:
    """클래스 레벨 공유 이벤트 루프 테스트"""

    def setup_method(self):
        """각 테스트 전에 공유 루프를 리셋"""
        ClaudeAgentRunner._reset_shared_loop()

    def test_ensure_loop_creates_loop(self):
        """_ensure_loop()가 이벤트 루프를 생성하는지 확인"""
        ClaudeAgentRunner._ensure_loop()

        assert ClaudeAgentRunner._shared_loop is not None
        assert ClaudeAgentRunner._shared_loop.is_running()

    def test_ensure_loop_creates_daemon_thread(self):
        """_ensure_loop()가 데몬 스레드를 생성하는지 확인"""
        ClaudeAgentRunner._ensure_loop()

        assert ClaudeAgentRunner._loop_thread is not None
        assert ClaudeAgentRunner._loop_thread.is_alive()
        assert ClaudeAgentRunner._loop_thread.daemon is True

    def test_ensure_loop_reuses_existing(self):
        """_ensure_loop()가 기존 루프를 재사용하는지 확인"""
        ClaudeAgentRunner._ensure_loop()
        first_loop = ClaudeAgentRunner._shared_loop
        first_thread = ClaudeAgentRunner._loop_thread

        ClaudeAgentRunner._ensure_loop()
        assert ClaudeAgentRunner._shared_loop is first_loop
        assert ClaudeAgentRunner._loop_thread is first_thread

    def test_ensure_loop_recreates_if_closed(self):
        """루프가 닫혀있으면 새로 생성하는지 확인"""
        ClaudeAgentRunner._ensure_loop()
        old_loop = ClaudeAgentRunner._shared_loop

        # 루프를 강제로 닫기
        old_loop.call_soon_threadsafe(old_loop.stop)
        ClaudeAgentRunner._loop_thread.join(timeout=2)

        ClaudeAgentRunner._ensure_loop()
        assert ClaudeAgentRunner._shared_loop is not old_loop
        assert ClaudeAgentRunner._shared_loop.is_running()

    def test_shared_loop_is_class_level(self):
        """공유 루프가 인스턴스가 아닌 클래스 레벨인지 확인"""
        runner1 = ClaudeAgentRunner()
        runner2 = ClaudeAgentRunner()

        ClaudeAgentRunner._ensure_loop()

        # 두 인스턴스가 같은 루프를 바라봄
        assert ClaudeAgentRunner._shared_loop is not None
        assert id(runner1._shared_loop) == id(runner2._shared_loop)


class TestRunSync:
    """run_sync() 브릿지 메서드 테스트"""

    def setup_method(self):
        """각 테스트 전에 공유 루프를 리셋"""
        ClaudeAgentRunner._reset_shared_loop()

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

    def test_run_sync_ensures_loop_automatically(self):
        """run_sync()가 자동으로 루프를 생성하는지 확인"""
        runner = ClaudeAgentRunner()
        assert ClaudeAgentRunner._shared_loop is None

        async def coro():
            return "auto-loop"

        result = runner.run_sync(coro())
        assert result == "auto-loop"
        assert ClaudeAgentRunner._shared_loop is not None
        assert ClaudeAgentRunner._shared_loop.is_running()

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
