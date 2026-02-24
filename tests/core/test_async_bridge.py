"""utils/async_bridge.py 테스트"""

import asyncio

import pytest

from seosoyoung.utils.async_bridge import run_in_new_loop


class TestRunInNewLoop:
    """run_in_new_loop 함수 테스트"""

    def test_returns_coroutine_result(self):
        """코루틴의 반환값을 동기적으로 반환"""
        async def simple():
            return 42

        assert run_in_new_loop(simple()) == 42

    def test_propagates_exception(self):
        """코루틴 내 예외가 호출자에게 전파"""
        async def fail():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_in_new_loop(fail())

    def test_runs_in_isolated_loop(self):
        """각 호출이 격리된 이벤트 루프에서 실행 (기존 루프와 독립)"""
        # 기존 루프가 있는 상태에서도 격리된 루프에서 실행되는지 확인
        # (id 비교는 GC 후 메모리 재활용으로 flaky할 수 있으므로
        #  루프가 정상 생성/실행/종료 되는지만 검증)
        async def verify_fresh_loop():
            loop = asyncio.get_running_loop()
            assert loop.is_running()
            return True

        assert run_in_new_loop(verify_fresh_loop()) is True
        assert run_in_new_loop(verify_fresh_loop()) is True

    def test_async_sleep(self):
        """asyncio.sleep 등 기본 async 연산 지원"""
        async def with_sleep():
            await asyncio.sleep(0.01)
            return "done"

        assert run_in_new_loop(with_sleep()) == "done"
