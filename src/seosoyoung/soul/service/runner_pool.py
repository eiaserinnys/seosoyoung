"""ClaudeRunner 풀링 시스템

매 요청마다 발생하는 콜드 스타트를 제거하기 위해 ClaudeRunner 인스턴스를 풀링합니다.

## 풀 구조
- session pool: OrderedDict[session_id, (ClaudeRunner, last_used)] — LRU 캐시
- generic pool: deque[(ClaudeRunner, idle_since)] — pre-warm 클라이언트 큐

## 크기 제한
max_size는 idle pool (session + generic) 합산 크기를 제한합니다.
"""

import asyncio
import logging
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner

logger = logging.getLogger(__name__)


class ClaudeRunnerPool:
    """ClaudeRunner 인스턴스 LRU 풀

    LRU 기반 세션 풀과 제네릭 풀을 함께 관리합니다.
    session_id가 있으면 같은 Claude 세션을 재사용하고,
    없으면 pre-warm된 generic runner를 재사용합니다.
    """

    def __init__(
        self,
        max_size: int = 5,
        idle_ttl: float = 300.0,
        workspace_dir: str = "",
        allowed_tools: Optional[list] = None,
        disallowed_tools: Optional[list] = None,
        mcp_config_path: Optional[Path] = None,
        min_generic: int = 1,
        maintenance_interval: float = 60.0,
    ):
        self._max_size = max_size
        self._idle_ttl = idle_ttl
        self._workspace_dir = workspace_dir
        self._allowed_tools = allowed_tools
        self._disallowed_tools = disallowed_tools
        self._mcp_config_path = mcp_config_path
        self._min_generic = min_generic
        self._maintenance_interval = maintenance_interval

        # session pool: session_id → (runner, last_used_time)
        # OrderedDict 순서 = 삽입/갱신 순서 → 첫 번째 항목이 LRU
        self._session_pool: OrderedDict[str, tuple[ClaudeRunner, float]] = OrderedDict()

        # generic pool: (runner, idle_since_time), 왼쪽이 oldest
        self._generic_pool: deque[tuple[ClaudeRunner, float]] = deque()

        # 통계
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

        self._lock = asyncio.Lock()

        # 유지보수 루프 태스크 참조
        self._maintenance_task: Optional[asyncio.Task] = None

    # -------------------------------------------------------------------------
    # 내부 헬퍼
    # -------------------------------------------------------------------------

    def _total_size(self) -> int:
        """현재 idle pool 총 크기"""
        return len(self._session_pool) + len(self._generic_pool)

    def _make_runner(self) -> ClaudeRunner:
        """새 ClaudeRunner 인스턴스 생성 (pooled=True)"""
        return ClaudeRunner(
            thread_ts="",
            working_dir=Path(self._workspace_dir) if self._workspace_dir else None,
            allowed_tools=self._allowed_tools,
            disallowed_tools=self._disallowed_tools,
            mcp_config_path=self._mcp_config_path,
            pooled=True,
        )

    async def _discard(self, runner: ClaudeRunner, reason: str = "") -> None:
        """runner를 안전하게 폐기"""
        try:
            await runner._remove_client()
        except Exception as e:
            logger.warning(f"Runner 폐기 중 오류 ({reason}): {e}")

    async def _evict_lru_unlocked(self) -> None:
        """LRU runner를 퇴거 (락 없이 — 이미 락을 보유한 상태에서 호출)"""
        if self._session_pool:
            # OrderedDict의 첫 번째 = 가장 오래된 (LRU)
            oldest_key, (runner, _) = next(iter(self._session_pool.items()))
            del self._session_pool[oldest_key]
            self._evictions += 1
            logger.info(
                f"LRU evict: session_id={oldest_key} | 이유=pool_full | "
                f"total_evictions={self._evictions} | "
                f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}, max={self._max_size}"
            )
            await self._discard(runner, reason=f"evict_lru session={oldest_key}")
        elif self._generic_pool:
            runner, _ = self._generic_pool.popleft()
            self._evictions += 1
            logger.info(
                f"LRU evict: generic | 이유=pool_full | "
                f"total_evictions={self._evictions} | "
                f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}, max={self._max_size}"
            )
            await self._discard(runner, reason="evict_lru generic")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def acquire(self, session_id: Optional[str] = None) -> ClaudeRunner:
        """풀에서 runner 획득

        - session_id 있음 → session pool에서 LRU hit 시도 → miss면 generic fallback → 없으면 new
        - session_id 없음 → generic pool에서 꺼내기 → 없으면 new
        - 풀 full → LRU evict 후 new 생성
        """
        t0 = time.monotonic()
        async with self._lock:
            now = time.monotonic()

            if session_id is not None:
                if session_id in self._session_pool:
                    runner, last_used = self._session_pool.pop(session_id)
                    if now - last_used <= self._idle_ttl:
                        self._hits += 1
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        logger.info(
                            f"Pool acquire HIT: session_id={session_id} | "
                            f"소요={elapsed_ms:.1f}ms | "
                            f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                        )
                        return runner
                    # TTL 만료 — 폐기
                    logger.info(f"Pool acquire: session TTL 만료, 폐기 | session_id={session_id}")
                    await self._discard(runner, reason=f"ttl_expired session={session_id}")

                self._misses += 1
                logger.info(
                    f"Pool acquire MISS: session_id={session_id} | "
                    f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                )

            # generic pool에서 TTL 유효한 runner 찾기
            while self._generic_pool:
                runner, idle_since = self._generic_pool.popleft()
                if now - idle_since <= self._idle_ttl:
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    logger.info(
                        f"Pool acquire GENERIC: session_id={session_id} | "
                        f"소요={elapsed_ms:.1f}ms | "
                        f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                    )
                    return runner
                # TTL 만료 — 폐기
                logger.info("Pool acquire: generic TTL 만료, 폐기")
                await self._discard(runner, reason="ttl_expired generic")

            # 새 runner 생성 — idle pool이 가득 찼으면 LRU 퇴거
            if self._total_size() >= self._max_size:
                await self._evict_lru_unlocked()

            runner = self._make_runner()
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                f"Pool acquire NEW: session_id={session_id} | "
                f"소요={elapsed_ms:.1f}ms | "
                f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
            )
            return runner

    async def release(
        self,
        runner: ClaudeRunner,
        session_id: Optional[str] = None,
    ) -> None:
        """실행 완료 후 runner 반환

        - session_id 있으면 session pool에 저장 (LRU update)
        - 없으면 generic pool에 반환
        - 풀 full → LRU evict 후 저장
        """
        async with self._lock:
            now = time.monotonic()

            # idle pool이 가득 찼으면 LRU 퇴거
            if self._total_size() >= self._max_size:
                await self._evict_lru_unlocked()

            if session_id is not None:
                # session pool: 기존 항목 제거 후 최신으로 삽입 (LRU update)
                if session_id in self._session_pool:
                    old_runner, _ = self._session_pool.pop(session_id)
                    if old_runner is not runner:
                        await self._discard(old_runner, reason=f"session replace: {session_id}")
                self._session_pool[session_id] = (runner, now)
                logger.info(
                    f"Pool release → session: session_id={session_id} | "
                    f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                )
            else:
                self._generic_pool.append((runner, now))
                logger.info(
                    f"Pool release → generic | "
                    f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                )

    async def evict_lru(self) -> None:
        """가장 오래 사용되지 않은 runner를 disconnect & 제거 (공개 API)"""
        async with self._lock:
            await self._evict_lru_unlocked()

    async def pre_warm(self, count: int) -> int:
        """N개의 generic runner를 미리 생성하여 generic pool에 추가

        각 runner는 ClaudeRunner(pooled=True)로 생성 후 _get_or_create_client()를 호출합니다.
        에러는 로그만 남기고 계속 진행합니다 (부분 예열 허용).

        Returns:
            성공적으로 예열된 runner 수
        """
        if count <= 0:
            return 0

        success = 0
        failed = 0
        for i in range(count):
            try:
                runner = self._make_runner()
                await runner._get_or_create_client()
                async with self._lock:
                    now = time.monotonic()
                    if self._total_size() >= self._max_size:
                        await self._evict_lru_unlocked()
                    self._generic_pool.append((runner, now))
                success += 1
                logger.info(
                    f"Pre-warm: runner {i + 1}/{count} 예열 완료 | "
                    f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
                )
            except Exception as e:
                failed += 1
                logger.warning(f"Pre-warm: runner {i + 1}/{count} 예열 실패 (계속 진행): {e}")

        logger.info(f"Pre-warm 완료: 성공={success}, 실패={failed}, 요청={count}")
        return success

    async def _run_maintenance(self) -> None:
        """유지보수 작업 1회 실행

        - TTL 초과 유휴 runner 정리 (session + generic)
        - 죽은 subprocess 감지 및 제거
        - generic pool이 min_generic 미만이면 보충
        """
        now = time.monotonic()
        to_discard: list[tuple[ClaudeRunner, str]] = []

        async with self._lock:
            # --- generic pool 정리 ---
            new_generic: deque[tuple[ClaudeRunner, float]] = deque()
            while self._generic_pool:
                runner, idle_since = self._generic_pool.popleft()
                # TTL 초과 확인
                if now - idle_since > self._idle_ttl:
                    to_discard.append((runner, "generic ttl_expired"))
                    continue
                # 죽은 subprocess 감지
                if not runner._is_cli_alive():
                    to_discard.append((runner, "generic dead_subprocess"))
                    continue
                new_generic.append((runner, idle_since))
            self._generic_pool = new_generic

            # --- session pool 정리 ---
            dead_sessions: list[str] = []
            for session_id, (runner, last_used) in list(self._session_pool.items()):
                if now - last_used > self._idle_ttl:
                    dead_sessions.append(session_id)
                    to_discard.append((runner, f"session ttl_expired: {session_id}"))
                elif not runner._is_cli_alive():
                    dead_sessions.append(session_id)
                    to_discard.append((runner, f"session dead_subprocess: {session_id}"))

            for session_id in dead_sessions:
                del self._session_pool[session_id]

        # 락 바깥에서 discard (disconnect는 느릴 수 있음)
        for runner, reason in to_discard:
            await self._discard(runner, reason=reason)

        if to_discard:
            reasons = [reason for _, reason in to_discard]
            logger.info(
                f"Maintenance: {len(to_discard)}개 runner 정리 | 이유={reasons} | "
                f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
            )
        else:
            logger.debug(
                f"Maintenance: 정리 없음 | "
                f"pool: session={len(self._session_pool)}, generic={len(self._generic_pool)}"
            )

        # --- generic pool 보충 ---
        async with self._lock:
            current_generic = len(self._generic_pool)

        shortage = self._min_generic - current_generic
        if shortage > 0:
            logger.info(
                f"Maintenance: generic pool 보충 필요 ({current_generic} < {self._min_generic})"
            )
            replenished = await self.pre_warm(shortage)
            if replenished > 0:
                logger.info(f"Maintenance: {replenished}개 generic runner 보충 완료")

    async def _maintenance_loop(self) -> None:
        """백그라운드 유지보수 루프

        _maintenance_interval 초마다 _run_maintenance()를 호출합니다.
        asyncio.CancelledError가 발생하면 정상 종료합니다.
        """
        logger.info(f"Maintenance loop 시작 (interval={self._maintenance_interval}s)")
        try:
            while True:
                await asyncio.sleep(self._maintenance_interval)
                try:
                    await self._run_maintenance()
                except Exception as e:
                    logger.error(f"Maintenance loop 오류 (계속 진행): {e}")
        except asyncio.CancelledError:
            logger.info("Maintenance loop 종료")

    async def start_maintenance(self) -> None:
        """유지보수 루프 백그라운드 태스크 시작

        이미 실행 중인 경우 중복 시작하지 않습니다.
        """
        if self._maintenance_task is not None and not self._maintenance_task.done():
            logger.debug("Maintenance loop already running, skipping start")
            return
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        logger.info("Maintenance loop task started")

    async def shutdown(self) -> int:
        """모든 runner disconnect 및 유지보수 루프 취소

        Returns:
            종료된 runner 수
        """
        # 유지보수 루프 취소
        if self._maintenance_task and not self._maintenance_task.done():
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
            self._maintenance_task = None

        async with self._lock:
            count = 0

            for session_id, (runner, _) in list(self._session_pool.items()):
                try:
                    await runner._remove_client()
                    count += 1
                except Exception as e:
                    logger.warning(f"Shutdown: session runner {session_id} 종료 실패: {e}")
            self._session_pool.clear()

            while self._generic_pool:
                runner, _ = self._generic_pool.popleft()
                try:
                    await runner._remove_client()
                    count += 1
                except Exception as e:
                    logger.warning(f"Shutdown: generic runner 종료 실패: {e}")

            logger.info(f"Pool shutdown: {count}개 runner 종료")
            return count

    def stats(self) -> dict:
        """현재 풀 상태 반환

        Returns:
            session_count: session pool 크기
            generic_count: generic pool 크기
            total: idle pool 합산 크기
            max_size: 풀 크기 한도
            hits: pool hit 횟수
            misses: pool miss 횟수
            evictions: LRU 퇴거 횟수
        """
        return {
            "session_count": len(self._session_pool),
            "generic_count": len(self._generic_pool),
            "total": self._total_size(),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
        }
