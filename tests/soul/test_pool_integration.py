"""
test_pool_integration - ClaudeRunnerPool 통합 테스트

풀 + 어댑터(SoulEngineAdapter)의 acquire/release 흐름,
동시성 시나리오, 세션 어피니티를 검증합니다.

ClaudeRunner는 mock으로 대체하여 실제 subprocess 없이 테스트합니다.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.soul.models import CompleteEvent, ErrorEvent
from seosoyoung.soul.service.engine_adapter import SoulEngineAdapter
from seosoyoung.soul.service.runner_pool import ClaudeRunnerPool
from seosoyoung.slackbot.claude.engine_types import EngineResult


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def make_mock_runner(
    session_id: str = "sess-default",
    success: bool = True,
    error: str = "",
):
    """ClaudeRunner 대역 생성"""
    runner = MagicMock()
    runner._remove_client = AsyncMock()
    runner._get_or_create_client = AsyncMock()
    runner._is_cli_alive.return_value = True

    result = EngineResult(
        success=success,
        output="완료" if success else "",
        session_id=session_id if success else None,
        error=error if not success else None,
    )
    runner.run = AsyncMock(return_value=result)
    return runner


async def collect_events(adapter: SoulEngineAdapter, prompt: str, **kwargs) -> list:
    events = []
    async for event in adapter.execute(prompt, **kwargs):
        events.append(event)
    return events


# ─────────────────────────────────────────────
# 새 세션: generic pool에서 acquire → 실행 → release with session_id
# ─────────────────────────────────────────────


class TestNewSessionFlow:
    async def test_new_session_acquires_from_generic_pool(self):
        """새 세션: generic pool에서 acquire → 성공 시 session pool로 release"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="new-sess-1")

        # generic pool에 미리 runner 추가
        pool._generic_pool.append((runner, time.monotonic()))

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(adapter, "새 작업")

        # CompleteEvent 확인
        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1
        assert complete_events[0].claude_session_id == "new-sess-1"

        # runner가 session pool로 반환됨
        assert "new-sess-1" in pool._session_pool
        assert pool.stats()["generic_count"] == 0
        assert pool.stats()["session_count"] == 1

    async def test_new_session_with_empty_pool_creates_runner(self):
        """풀이 비어있을 때: 새 runner 생성 후 session pool로 release"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="fresh-sess")

        with patch.object(pool, "_make_runner", return_value=runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
            events = await collect_events(adapter, "첫 작업")

        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1
        assert complete_events[0].claude_session_id == "fresh-sess"

        # session pool에 저장됨
        assert "fresh-sess" in pool._session_pool


# ─────────────────────────────────────────────
# 컨티뉴: session pool에서 hit → 즉시 실행 → release
# ─────────────────────────────────────────────


class TestContinueSessionFlow:
    async def test_continue_session_hits_session_pool(self):
        """컨티뉴: session pool에서 hit → 재사용"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="existing-sess")

        # session pool에 미리 저장
        pool._session_pool["existing-sess"] = (runner, time.monotonic())

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(
            adapter, "이어서 작업", resume_session_id="existing-sess"
        )

        # CompleteEvent 확인
        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1

        # 풀 hit 카운트 증가
        assert pool.stats()["hits"] == 1
        assert pool.stats()["misses"] == 0

    async def test_continue_session_reacquires_same_runner(self):
        """같은 session_id로 두 번 실행하면 같은 runner를 재사용"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)

        # 첫 번째 실행용 runner
        runner = make_mock_runner(session_id="repeat-sess")
        with patch.object(pool, "_make_runner", return_value=runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)

            # 첫 번째 실행 (new)
            events1 = await collect_events(
                adapter, "작업 1", resume_session_id="repeat-sess"
            )

        # 두 번째 실행: session pool에서 hit
        adapter2 = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events2 = await collect_events(
            adapter2, "작업 2", resume_session_id="repeat-sess"
        )

        # 두 번째 실행 시 runner.run이 2번 호출됨 (같은 runner 재사용)
        assert runner.run.await_count == 2
        assert pool.stats()["hits"] == 1


# ─────────────────────────────────────────────
# 세션 miss: generic에서 fallback → 실행 → release
# ─────────────────────────────────────────────


class TestSessionMissFlow:
    async def test_session_miss_falls_back_to_generic(self):
        """session miss → generic pool fallback 후 session_id로 release"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="fallback-sess")

        # session pool에는 없음, generic pool에 있음
        pool._generic_pool.append((runner, time.monotonic()))

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(
            adapter, "이어서", resume_session_id="fallback-sess"
        )

        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1

        # miss 카운트 증가
        assert pool.stats()["misses"] == 1

        # session pool에 저장됨
        assert "fallback-sess" in pool._session_pool

    async def test_session_miss_no_generic_creates_new_runner(self):
        """session miss, generic도 없음 → 새 runner 생성"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="brand-new")

        with patch.object(pool, "_make_runner", return_value=runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
            events = await collect_events(
                adapter, "작업", resume_session_id="brand-new"
            )

        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1

        # miss + 새 생성
        assert pool.stats()["misses"] == 1
        assert "brand-new" in pool._session_pool


# ─────────────────────────────────────────────
# 풀 full: LRU evict 후 acquire 성공
# ─────────────────────────────────────────────


class TestPoolFullEviction:
    async def test_pool_full_evicts_lru_on_new_session(self):
        """풀이 가득 찼을 때 새 세션 요청 → LRU evict 후 성공"""
        pool = ClaudeRunnerPool(max_size=2, idle_ttl=300.0)

        # 풀을 max_size까지 채움
        r1 = make_mock_runner(session_id="old-1")
        r2 = make_mock_runner(session_id="old-2")
        pool._session_pool["old-1"] = (r1, time.monotonic() - 100)  # 오래됨 (LRU)
        pool._session_pool["old-2"] = (r2, time.monotonic())

        assert pool.stats()["total"] == 2  # full

        # 새 세션 요청
        new_runner = make_mock_runner(session_id="new-one")
        with patch.object(pool, "_make_runner", return_value=new_runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
            events = await collect_events(adapter, "새 작업")

        # eviction 발생
        assert pool.stats()["evictions"] == 1
        # old-1이 퇴거됨
        assert "old-1" not in pool._session_pool
        # 새 세션 저장됨
        assert "new-one" in pool._session_pool

        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1

    async def test_pool_full_evicts_on_release(self):
        """release 시점에도 풀 full이면 evict"""
        pool = ClaudeRunnerPool(max_size=2, idle_ttl=300.0)

        r1 = make_mock_runner(session_id="sess-a")
        r2 = make_mock_runner(session_id="sess-b")
        # 미리 풀을 가득 채움
        pool._session_pool["sess-a"] = (r1, time.monotonic() - 100)
        pool._session_pool["sess-b"] = (r2, time.monotonic())

        # 새 runner를 release → evict 발생해야 함
        new_runner = make_mock_runner(session_id="sess-c")
        await pool.release(new_runner, session_id="sess-c")

        assert pool.stats()["evictions"] == 1
        assert pool.stats()["total"] == 2
        assert "sess-c" in pool._session_pool


# ─────────────────────────────────────────────
# 에러 시: runner 폐기 (풀에 반환 안 됨)
# ─────────────────────────────────────────────


class TestErrorDiscardsRunner:
    async def test_runner_not_returned_to_pool_on_error(self):
        """실패한 실행 후 runner는 풀에 반환되지 않음"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)

        # 실패하는 runner
        error_runner = make_mock_runner(success=False, error="실행 실패")
        pool._generic_pool.append((error_runner, time.monotonic()))

        initial_stats = pool.stats()
        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(adapter, "실패할 작업")

        # ErrorEvent 확인
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1

        # runner가 풀에 반환되지 않음
        assert pool.stats()["session_count"] == 0
        assert pool.stats()["generic_count"] == 0
        assert pool.stats()["total"] == 0

    async def test_runner_not_returned_on_is_error(self):
        """is_error=True 결과 시 runner 폐기"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)

        runner = MagicMock()
        runner._remove_client = AsyncMock()
        runner._get_or_create_client = AsyncMock()
        runner._is_cli_alive.return_value = True
        runner.run = AsyncMock(return_value=EngineResult(
            success=True,
            output="error text",
            is_error=True,
            error="engine error",
        ))
        pool._generic_pool.append((runner, time.monotonic()))

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(adapter, "오류 작업")

        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert pool.stats()["total"] == 0

    async def test_runner_not_returned_on_exception(self):
        """예외 발생 시 runner 폐기"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)

        runner = MagicMock()
        runner._remove_client = AsyncMock()
        runner._get_or_create_client = AsyncMock()
        runner._is_cli_alive.return_value = True
        runner.run = AsyncMock(side_effect=RuntimeError("runner crashed"))
        pool._generic_pool.append((runner, time.monotonic()))

        adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
        events = await collect_events(adapter, "충돌할 작업")

        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert pool.stats()["total"] == 0


# ─────────────────────────────────────────────
# 풀 없는 모드: 기존 동작 동일 (하위호환)
# ─────────────────────────────────────────────


class TestNoPoolMode:
    async def test_no_pool_creates_runner_directly(self):
        """pool=None이면 ClaudeRunner 직접 생성 (하위호환)"""
        adapter = SoulEngineAdapter(workspace_dir="/test", pool=None)
        mock_result = EngineResult(success=True, output="직접 실행 완료", session_id="direct-1")

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(return_value=mock_result)

            events = await collect_events(adapter, "직접 실행")

        assert MockRunner.called
        complete_events = [e for e in events if isinstance(e, CompleteEvent)]
        assert len(complete_events) == 1
        assert complete_events[0].result == "직접 실행 완료"

    async def test_no_pool_error_does_not_affect_pool(self):
        """pool=None 모드에서 에러 발생해도 풀 영향 없음"""
        adapter = SoulEngineAdapter(workspace_dir="/test", pool=None)

        with patch(
            "seosoyoung.soul.service.engine_adapter.ClaudeRunner"
        ) as MockRunner:
            instance = MockRunner.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("직접 실행 오류"))

            events = await collect_events(adapter, "오류 발생")

        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1


# ─────────────────────────────────────────────
# 동시성 테스트
# ─────────────────────────────────────────────


class TestConcurrency:
    async def test_concurrent_acquire_no_race_condition(self):
        """여러 태스크가 동시에 acquire — 각각 다른 runner 받음"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)

        # 5개의 다른 runner를 _make_runner가 순서대로 반환
        runners = [make_mock_runner(session_id=f"c-sess-{i}") for i in range(5)]
        call_idx = 0

        def make_runner():
            nonlocal call_idx
            r = runners[call_idx]
            call_idx += 1
            return r

        with patch.object(pool, "_make_runner", side_effect=make_runner):
            # 5개 동시 acquire
            acquired = await asyncio.gather(*[
                pool.acquire(session_id=f"c-sess-{i}") for i in range(5)
            ])

        # 모두 다른 runner
        assert len(set(id(r) for r in acquired)) == 5

    async def test_concurrent_acquire_release_consistent_stats(self):
        """동시 acquire/release 후 풀 크기가 일관됨"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runners = [make_mock_runner(session_id=f"cr-{i}") for i in range(3)]
        idx = 0

        def make_runner():
            nonlocal idx
            r = runners[idx % len(runners)]
            idx += 1
            return r

        with patch.object(pool, "_make_runner", side_effect=make_runner):
            # acquire 3개
            acquired = await asyncio.gather(*[
                pool.acquire(session_id=f"cr-{i}") for i in range(3)
            ])

        # 모두 release
        await asyncio.gather(*[
            pool.release(r, session_id=f"cr-{i}") for i, r in enumerate(acquired)
        ])

        # pool 크기가 max_size 이하
        s = pool.stats()
        assert s["total"] <= s["max_size"]

    async def test_concurrent_access_to_full_pool_evicts_lru(self):
        """풀 full 상태에서 동시 acquire → LRU evict 후 성공"""
        pool = ClaudeRunnerPool(max_size=2, idle_ttl=300.0)

        # 풀을 가득 채움
        r1 = make_mock_runner(session_id="full-1")
        r2 = make_mock_runner(session_id="full-2")
        pool._session_pool["full-1"] = (r1, time.monotonic() - 200)
        pool._session_pool["full-2"] = (r2, time.monotonic() - 100)

        new_runners = [make_mock_runner(session_id=f"new-{i}") for i in range(2)]
        idx = 0

        def make_runner():
            nonlocal idx
            r = new_runners[idx % len(new_runners)]
            idx += 1
            return r

        with patch.object(pool, "_make_runner", side_effect=make_runner):
            # 두 태스크가 동시에 새 세션 요청
            r_a, r_b = await asyncio.gather(
                pool.acquire(session_id="extra-a"),
                pool.acquire(session_id="extra-b"),
            )

        # eviction이 최소 1회 발생
        assert pool.stats()["evictions"] >= 1
        # 반환된 두 runner가 None이 아님
        assert r_a is not None
        assert r_b is not None

    async def test_many_concurrent_adapters_no_crash(self):
        """여러 어댑터가 동시에 풀을 사용해도 충돌 없음"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        call_count = 0

        def make_runner():
            nonlocal call_count
            r = make_mock_runner(session_id=f"multi-{call_count}")
            call_count += 1
            return r

        adapters = [SoulEngineAdapter(workspace_dir="/test", pool=pool) for _ in range(5)]

        with patch.object(pool, "_make_runner", side_effect=make_runner):
            results = await asyncio.gather(*[
                collect_events(adapter, f"작업 {i}")
                for i, adapter in enumerate(adapters)
            ])

        # 모두 CompleteEvent로 끝남
        for events in results:
            complete_events = [e for e in events if isinstance(e, CompleteEvent)]
            assert len(complete_events) == 1


# ─────────────────────────────────────────────
# 세션 어피니티
# ─────────────────────────────────────────────


class TestSessionAffinity:
    async def test_same_session_id_returns_same_runner(self):
        """같은 session_id로 연속 호출 → 같은 runner 재사용"""
        pool = ClaudeRunnerPool(max_size=3, idle_ttl=300.0)
        runner = make_mock_runner(session_id="affinity-sess")

        with patch.object(pool, "_make_runner", return_value=runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)

            # 첫 번째 실행
            await collect_events(adapter, "첫 번째", resume_session_id="affinity-sess")
            # 두 번째 실행 (같은 session_id)
            await collect_events(adapter, "두 번째", resume_session_id="affinity-sess")

        # 같은 runner가 두 번 사용됨
        assert runner.run.await_count == 2
        # hit이 1번 발생 (두 번째 acquire에서)
        assert pool.stats()["hits"] == 1

    async def test_different_session_ids_use_different_runners(self):
        """다른 session_id는 다른 runner를 사용"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        r1 = make_mock_runner(session_id="sid-A")
        r2 = make_mock_runner(session_id="sid-B")

        call_idx = 0
        runners = [r1, r2]

        def make_runner():
            nonlocal call_idx
            r = runners[call_idx % len(runners)]
            call_idx += 1
            return r

        with patch.object(pool, "_make_runner", side_effect=make_runner):
            adapter = SoulEngineAdapter(workspace_dir="/test", pool=pool)
            await collect_events(adapter, "A 작업", resume_session_id="sid-A")
            await collect_events(adapter, "B 작업", resume_session_id="sid-B")

        # 두 runner 모두 1번씩 사용됨
        assert r1.run.await_count == 1
        assert r2.run.await_count == 1
        assert "sid-A" in pool._session_pool
        assert "sid-B" in pool._session_pool
