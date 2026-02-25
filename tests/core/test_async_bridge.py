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
        """각 호출이 격리된 이벤트 루프에서 실행"""
        # id()는 GC 후 재사용될 수 있으므로, 루프 객체를 직접 보관하여
        # GC를 방지한 뒤 identity를 비교한다.
        loops = []

        async def capture_loop():
            loop = asyncio.get_running_loop()
            loops.append(loop)
            return True

        run_in_new_loop(capture_loop())
        run_in_new_loop(capture_loop())

        assert len(loops) == 2
        assert loops[0] is not loops[1], "각 호출이 서로 다른 이벤트 루프를 사용해야 함"

    def test_async_sleep(self):
        """asyncio.sleep 등 기본 async 연산 지원"""
        async def with_sleep():
            await asyncio.sleep(0.01)
            return "done"

        assert run_in_new_loop(with_sleep()) == "done"
