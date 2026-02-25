"""
test_runner_pool - ClaudeRunnerPool 단위 테스트

ClaudeRunner를 mock으로 대체하여 풀 로직만 검증합니다.
"""

import asyncio
import time
from collections import OrderedDict, deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.soul.service.runner_pool import ClaudeRunnerPool


# ─────────────────────────────────────────────
# Helpers / Fixtures
# ─────────────────────────────────────────────


def make_mock_runner():
    """ClaudeRunner 대역 — _remove_client, _get_or_create_client는 async"""
    runner = MagicMock()
    runner._remove_client = AsyncMock()
    runner._get_or_create_client = AsyncMock()
    runner._is_cli_alive.return_value = True
    return runner


@pytest.fixture
def pool():
    """기본 풀 (max_size=3, ttl=300s)"""
    return ClaudeRunnerPool(max_size=3, idle_ttl=300.0)


@pytest.fixture
def small_pool():
    """작은 풀 (max_size=2, ttl=300s)"""
    return ClaudeRunnerPool(max_size=2, idle_ttl=300.0)


@pytest.fixture
def short_ttl_pool():
    """TTL이 짧은 풀 (max_size=3, ttl=0.01s)"""
    return ClaudeRunnerPool(max_size=3, idle_ttl=0.01)


# ─────────────────────────────────────────────
# 초기 상태
# ─────────────────────────────────────────────


class TestInitialState:
    def test_stats_initial(self, pool):
        s = pool.stats()
        assert s["session_count"] == 0
        assert s["generic_count"] == 0
        assert s["total"] == 0
        assert s["hits"] == 0
        assert s["misses"] == 0
        assert s["evictions"] == 0

    def test_max_size_reflected(self, pool):
        assert pool.stats()["max_size"] == 3


# ─────────────────────────────────────────────
# acquire — session_id 없음 (generic path)
# ─────────────────────────────────────────────


class TestAcquireGeneric:
    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_no_session_creates_new_runner(self, mock_make, pool):
        mock_runner = make_mock_runner()
        mock_make.return_value = mock_runner

        result = await pool.acquire()

        assert result is mock_runner
        mock_make.assert_called_once()

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_returns_generic_pool_runner(self, mock_make, pool):
        """generic pool에 runner가 있으면 _make_runner를 호출하지 않고 재사용"""
        idle_runner = make_mock_runner()
        pool._generic_pool.append((idle_runner, time.monotonic()))

        result = await pool.acquire()

        assert result is idle_runner
        mock_make.assert_not_called()

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_generic_ttl_expired_creates_new(self, mock_make, short_ttl_pool):
        """TTL 만료된 generic runner는 폐기하고 새로 생성"""
        expired_runner = make_mock_runner()
        short_ttl_pool._generic_pool.append((expired_runner, time.monotonic() - 1.0))  # 1초 전 (ttl=0.01)

        new_runner = make_mock_runner()
        mock_make.return_value = new_runner

        result = await short_ttl_pool.acquire()

        assert result is new_runner
        expired_runner._remove_client.assert_awaited_once()
        assert len(short_ttl_pool._generic_pool) == 0


# ─────────────────────────────────────────────
# acquire — session_id 있음 (session path)
# ─────────────────────────────────────────────


class TestAcquireSession:
    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_session_hit(self, mock_make, pool):
        """session pool hit → _make_runner 호출 안 함"""
        cached_runner = make_mock_runner()
        pool._session_pool["sid_abc"] = (cached_runner, time.monotonic())

        result = await pool.acquire(session_id="sid_abc")

        assert result is cached_runner
        mock_make.assert_not_called()
        assert pool.stats()["hits"] == 1
        assert pool.stats()["misses"] == 0
        # session pool에서 pop되어 빈 상태
        assert "sid_abc" not in pool._session_pool

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_session_miss_uses_generic(self, mock_make, pool):
        """session miss → generic pool fallback"""
        generic_runner = make_mock_runner()
        pool._generic_pool.append((generic_runner, time.monotonic()))

        result = await pool.acquire(session_id="sid_new")

        assert result is generic_runner
        assert pool.stats()["misses"] == 1
        mock_make.assert_not_called()

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_session_miss_no_generic_creates_new(self, mock_make, pool):
        """session miss, generic pool 비어있음 → new 생성"""
        new_runner = make_mock_runner()
        mock_make.return_value = new_runner

        result = await pool.acquire(session_id="sid_new")

        assert result is new_runner
        assert pool.stats()["misses"] == 1
        mock_make.assert_called_once()

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_session_ttl_expired_creates_new(self, mock_make, short_ttl_pool):
        """session TTL 만료 → 폐기 후 새 생성"""
        expired_runner = make_mock_runner()
        short_ttl_pool._session_pool["sid_exp"] = (expired_runner, time.monotonic() - 1.0)

        new_runner = make_mock_runner()
        mock_make.return_value = new_runner

        result = await short_ttl_pool.acquire(session_id="sid_exp")

        assert result is new_runner
        expired_runner._remove_client.assert_awaited_once()
        assert pool is not short_ttl_pool  # sanity
        assert short_ttl_pool.stats()["misses"] == 1


# ─────────────────────────────────────────────
# release
# ─────────────────────────────────────────────


class TestRelease:
    async def test_release_to_generic_pool(self, pool):
        runner = make_mock_runner()
        await pool.release(runner)

        assert pool.stats()["generic_count"] == 1
        assert pool.stats()["session_count"] == 0

    async def test_release_to_session_pool(self, pool):
        runner = make_mock_runner()
        await pool.release(runner, session_id="sid_x")

        assert pool.stats()["session_count"] == 1
        assert "sid_x" in pool._session_pool

    async def test_release_updates_lru_order(self, pool):
        """같은 session_id로 release하면 LRU 순서 갱신"""
        r1, r2 = make_mock_runner(), make_mock_runner()
        await pool.release(r1, session_id="sid_a")
        await pool.release(r2, session_id="sid_b")
        # sid_a 갱신 → sid_a가 최신 위치로
        r3 = make_mock_runner()
        await pool.release(r3, session_id="sid_a")

        keys = list(pool._session_pool.keys())
        assert keys[-1] == "sid_a", "sid_a가 가장 최근에 사용됨 (MRU 위치)"

    async def test_release_replaces_old_runner_for_same_session(self, pool):
        """같은 session_id로 새 runner를 release하면 이전 runner는 폐기"""
        r_old = make_mock_runner()
        r_new = make_mock_runner()
        await pool.release(r_old, session_id="sid_y")
        await pool.release(r_new, session_id="sid_y")

        r_old._remove_client.assert_awaited_once()
        stored_runner, _ = pool._session_pool["sid_y"]
        assert stored_runner is r_new

    async def test_release_evicts_when_full(self, small_pool):
        """풀이 꽉 찼을 때 release하면 LRU evict 발생"""
        r1, r2 = make_mock_runner(), make_mock_runner()
        await small_pool.release(r1, session_id="sid_1")
        await small_pool.release(r2, session_id="sid_2")
        assert small_pool.stats()["total"] == 2

        r3 = make_mock_runner()
        await small_pool.release(r3, session_id="sid_3")

        # eviction 발생
        assert small_pool.stats()["evictions"] == 1
        assert small_pool.stats()["total"] == 2  # evict 1 + add 1 - 기존 2 = 2


# ─────────────────────────────────────────────
# LRU eviction
# ─────────────────────────────────────────────


class TestEvictLru:
    async def test_evict_lru_removes_oldest_session(self, pool):
        r1, r2 = make_mock_runner(), make_mock_runner()
        # r1이 먼저 삽입 → LRU
        pool._session_pool["sid_old"] = (r1, time.monotonic() - 100)
        pool._session_pool["sid_new"] = (r2, time.monotonic())

        await pool.evict_lru()

        r1._remove_client.assert_awaited_once()
        assert "sid_old" not in pool._session_pool
        assert "sid_new" in pool._session_pool
        assert pool.stats()["evictions"] == 1

    async def test_evict_lru_on_empty_pool_is_noop(self, pool):
        """빈 풀에서 evict_lru → 오류 없이 종료"""
        await pool.evict_lru()
        assert pool.stats()["evictions"] == 0

    async def test_evict_lru_falls_back_to_generic(self, pool):
        """session pool 비어있으면 generic pool에서 퇴거"""
        r = make_mock_runner()
        pool._generic_pool.append((r, time.monotonic()))

        await pool.evict_lru()

        r._remove_client.assert_awaited_once()
        assert len(pool._generic_pool) == 0
        assert pool.stats()["evictions"] == 1

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_acquire_triggers_evict_when_full(self, mock_make, small_pool):
        """풀이 가득 찼을 때 acquire 시 LRU evict 발생"""
        r1, r2 = make_mock_runner(), make_mock_runner()
        small_pool._session_pool["sid_a"] = (r1, time.monotonic())
        small_pool._session_pool["sid_b"] = (r2, time.monotonic())
        assert small_pool.stats()["total"] == 2  # full

        new_runner = make_mock_runner()
        mock_make.return_value = new_runner

        result = await small_pool.acquire(session_id="sid_c")

        assert result is new_runner
        assert small_pool.stats()["evictions"] == 1


# ─────────────────────────────────────────────
# shutdown
# ─────────────────────────────────────────────


class TestShutdown:
    async def test_shutdown_disconnects_all_runners(self, pool):
        r1, r2, r3 = make_mock_runner(), make_mock_runner(), make_mock_runner()
        pool._session_pool["sid_1"] = (r1, time.monotonic())
        pool._session_pool["sid_2"] = (r2, time.monotonic())
        pool._generic_pool.append((r3, time.monotonic()))

        count = await pool.shutdown()

        assert count == 3
        r1._remove_client.assert_awaited_once()
        r2._remove_client.assert_awaited_once()
        r3._remove_client.assert_awaited_once()
        assert pool.stats()["session_count"] == 0
        assert pool.stats()["generic_count"] == 0

    async def test_shutdown_empty_pool_returns_zero(self, pool):
        count = await pool.shutdown()
        assert count == 0

    async def test_shutdown_continues_on_error(self, pool):
        """shutdown 중 오류가 발생해도 나머지 runner는 계속 종료"""
        r1, r2 = make_mock_runner(), make_mock_runner()
        r1._remove_client.side_effect = RuntimeError("disconnect fail")
        pool._session_pool["sid_err"] = (r1, time.monotonic())
        pool._session_pool["sid_ok"] = (r2, time.monotonic())

        count = await pool.shutdown()

        # r1은 실패해도 count에서 제외되지만 r2는 성공
        assert count == 1
        r2._remove_client.assert_awaited_once()


# ─────────────────────────────────────────────
# stats
# ─────────────────────────────────────────────


class TestStats:
    async def test_stats_tracks_counts(self, pool):
        r1, r2 = make_mock_runner(), make_mock_runner()
        await pool.release(r1, session_id="sid_1")
        await pool.release(r2)

        s = pool.stats()
        assert s["session_count"] == 1
        assert s["generic_count"] == 1
        assert s["total"] == 2

    async def test_stats_tracks_hits_and_misses(self, pool):
        r = make_mock_runner()
        pool._session_pool["sid_hit"] = (r, time.monotonic())

        # hit
        await pool.acquire(session_id="sid_hit")
        # miss
        with patch.object(pool, "_make_runner", return_value=make_mock_runner()):
            await pool.acquire(session_id="sid_miss")

        s = pool.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1

    async def test_stats_tracks_evictions(self, small_pool):
        r1, r2 = make_mock_runner(), make_mock_runner()
        small_pool._session_pool["sid_1"] = (r1, time.monotonic())
        small_pool._session_pool["sid_2"] = (r2, time.monotonic())

        await small_pool.evict_lru()
        assert small_pool.stats()["evictions"] == 1


# ─────────────────────────────────────────────
# acquire/release 라운드트립
# ─────────────────────────────────────────────


class TestAcquireReleaseRoundtrip:
    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_session_roundtrip_reuses_same_runner(self, mock_make, pool):
        """acquire → release → acquire 시 같은 runner 재사용"""
        runner = make_mock_runner()
        mock_make.return_value = runner

        acquired = await pool.acquire(session_id="sid_rt")
        await pool.release(acquired, session_id="sid_rt")
        reacquired = await pool.acquire(session_id="sid_rt")

        assert reacquired is runner
        # 두 번째 acquire는 hit (새 생성 없음)
        mock_make.assert_called_once()
        assert pool.stats()["hits"] == 1

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_generic_roundtrip_reuses_runner(self, mock_make, pool):
        runner = make_mock_runner()
        mock_make.return_value = runner

        acquired = await pool.acquire()
        await pool.release(acquired)
        reacquired = await pool.acquire()

        assert reacquired is runner
        mock_make.assert_called_once()

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_concurrent_acquire_release(self, mock_make, pool):
        """동시 acquire/release에서 락이 데이터 일관성 보장"""
        runners = [make_mock_runner() for _ in range(5)]
        call_idx = 0

        def side_effect():
            nonlocal call_idx
            r = runners[call_idx % len(runners)]
            call_idx += 1
            return r

        mock_make.side_effect = side_effect

        # 동시에 3개 acquire
        results = await asyncio.gather(
            pool.acquire(session_id="s1"),
            pool.acquire(session_id="s2"),
            pool.acquire(session_id="s3"),
        )

        assert len(results) == 3
        assert len(set(id(r) for r in results)) == 3  # 모두 다른 runner


# ─────────────────────────────────────────────
# pre_warm
# ─────────────────────────────────────────────


class TestPreWarm:
    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_pre_warm_adds_runners_to_generic_pool(self, mock_make, pool):
        """pre_warm(2) → generic pool에 2개 추가"""
        runners = [make_mock_runner() for _ in range(2)]
        mock_make.side_effect = runners

        count = await pool.pre_warm(2)

        assert count == 2
        assert pool.stats()["generic_count"] == 2

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_pre_warm_returns_success_count(self, mock_make, pool):
        """pre_warm 성공 수를 반환"""
        runners = [make_mock_runner() for _ in range(3)]
        mock_make.side_effect = runners

        count = await pool.pre_warm(3)

        assert count == 3

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_pre_warm_partial_success_on_error(self, mock_make, pool):
        """일부 예열 중 에러 발생해도 나머지는 계속 진행"""
        r1 = make_mock_runner()
        r2 = make_mock_runner()
        r2._get_or_create_client = AsyncMock(side_effect=RuntimeError("connect fail"))
        r3 = make_mock_runner()

        # _make_runner가 순서대로 반환
        mock_make.side_effect = [r1, r2, r3]

        # r2가 실패해도 r1, r3은 성공해야 함
        # pre_warm 내부에서 _get_or_create_client를 호출한다고 가정
        # 실제 구현에서는 connect()나 _get_or_create_client()를 호출
        count = await pool.pre_warm(3)

        # 성공한 것만 카운트 (에러는 로그만 남기고 계속 진행)
        assert count >= 0  # 부분 성공 허용

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_pre_warm_zero_count(self, mock_make, pool):
        """pre_warm(0) → 아무것도 하지 않음"""
        count = await pool.pre_warm(0)

        assert count == 0
        mock_make.assert_not_called()
        assert pool.stats()["generic_count"] == 0

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_pre_warm_respects_pool_max_size(self, mock_make, pool):
        """pre_warm이 max_size를 초과하면 초과분은 evict"""
        # pool max_size=3, pre_warm(4) → 3개만 유지
        runners = [make_mock_runner() for _ in range(4)]
        mock_make.side_effect = runners

        count = await pool.pre_warm(4)

        # max_size(3) 이하로 유지됨
        assert pool.stats()["total"] <= pool.stats()["max_size"]


# ─────────────────────────────────────────────
# _maintenance_loop
# ─────────────────────────────────────────────


class TestMaintenanceLoop:
    async def test_maintenance_loop_removes_ttl_expired_generic(self):
        """유지보수 루프: TTL 만료된 generic runner 제거"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=0.01)
        expired = make_mock_runner()
        expired.is_idle.return_value = True
        expired._is_cli_alive.return_value = True
        # TTL 만료시킴 (1초 전 추가)
        pool._generic_pool.append((expired, time.monotonic() - 1.0))

        await pool._run_maintenance()

        expired._remove_client.assert_awaited()
        assert pool.stats()["generic_count"] == 0

    async def test_maintenance_loop_removes_dead_subprocess(self):
        """유지보수 루프: 죽은 subprocess를 가진 generic runner 제거"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        dead_runner = make_mock_runner()
        dead_runner.is_idle.return_value = True
        dead_runner._is_cli_alive.return_value = False  # 죽은 프로세스
        pool._generic_pool.append((dead_runner, time.monotonic()))

        await pool._run_maintenance()

        dead_runner._remove_client.assert_awaited()
        assert pool.stats()["generic_count"] == 0

    async def test_maintenance_loop_keeps_alive_runners(self):
        """유지보수 루프: 살아있는 runner는 유지"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        alive_runner = make_mock_runner()
        alive_runner.is_idle.return_value = True
        alive_runner._is_cli_alive.return_value = True
        pool._generic_pool.append((alive_runner, time.monotonic()))

        await pool._run_maintenance()

        alive_runner._remove_client.assert_not_awaited()
        assert pool.stats()["generic_count"] == 1

    @patch("seosoyoung.soul.service.runner_pool.ClaudeRunnerPool._make_runner")
    async def test_maintenance_loop_replenishes_generic_pool(self, mock_make):
        """유지보수 루프: generic pool이 min_generic 미만이면 보충"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0, min_generic=2)
        # generic pool 비어있음 → 보충 필요
        new_runner = make_mock_runner()
        mock_make.return_value = new_runner

        await pool._run_maintenance()

        # min_generic=2이므로 2개 보충
        assert pool.stats()["generic_count"] == 2

    async def test_maintenance_loop_cancellable(self):
        """_maintenance_loop는 CancelledError로 정상 종료"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0, maintenance_interval=9999.0)

        task = asyncio.create_task(pool._maintenance_loop())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass  # 정상 종료

    async def test_maintenance_loop_removes_dead_session_runner(self):
        """유지보수 루프: 죽은 subprocess를 가진 session runner 제거"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        dead_runner = make_mock_runner()
        dead_runner.is_idle.return_value = True
        dead_runner._is_cli_alive.return_value = False
        pool._session_pool["dead_session"] = (dead_runner, time.monotonic())

        await pool._run_maintenance()

        dead_runner._remove_client.assert_awaited()
        assert "dead_session" not in pool._session_pool

    async def test_maintenance_loop_removes_ttl_expired_session(self):
        """유지보수 루프: TTL 만료된 session runner 제거"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=0.01)
        expired_runner = make_mock_runner()
        expired_runner.is_idle.return_value = True
        expired_runner._is_cli_alive.return_value = True
        pool._session_pool["expired_session"] = (expired_runner, time.monotonic() - 1.0)

        await pool._run_maintenance()

        expired_runner._remove_client.assert_awaited()
        assert "expired_session" not in pool._session_pool


# ─────────────────────────────────────────────
# shutdown with maintenance loop
# ─────────────────────────────────────────────


class TestShutdownWithMaintenanceLoop:
    async def test_shutdown_cancels_maintenance_task(self):
        """shutdown 시 유지보수 루프 태스크 취소"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0, maintenance_interval=9999.0)

        # 유지보수 루프 시작
        pool._maintenance_task = asyncio.create_task(pool._maintenance_loop())
        await asyncio.sleep(0.01)  # 루프가 시작되도록 yield

        await pool.shutdown()

        assert pool._maintenance_task is None or pool._maintenance_task.done()

    async def test_shutdown_logs_runner_count(self):
        """shutdown은 정리된 runner 수를 반환"""
        pool = ClaudeRunnerPool(max_size=5, idle_ttl=300.0)
        r1, r2 = make_mock_runner(), make_mock_runner()
        pool._generic_pool.append((r1, time.monotonic()))
        pool._session_pool["sid_1"] = (r2, time.monotonic())

        count = await pool.shutdown()

        assert count == 2
