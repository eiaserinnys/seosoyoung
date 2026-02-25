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
    ):
        self._max_size = max_size
        self._idle_ttl = idle_ttl
        self._workspace_dir = workspace_dir
        self._allowed_tools = allowed_tools
        self._disallowed_tools = disallowed_tools
        self._mcp_config_path = mcp_config_path

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

    # -------------------------------------------------------------------------
    # 내부 헬퍼
    # -------------------------------------------------------------------------

    def _total_size(self) -> int:
        """현재 idle pool 총 크기"""
        return len(self._session_pool) + len(self._generic_pool)

    def _make_runner(self) -> ClaudeRunner:
        """새 ClaudeRunner 인스턴스 생성"""
        return ClaudeRunner(
            thread_ts="",
            working_dir=Path(self._workspace_dir) if self._workspace_dir else None,
            allowed_tools=self._allowed_tools,
            disallowed_tools=self._disallowed_tools,
            mcp_config_path=self._mcp_config_path,
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
            logger.debug(f"LRU evict (session): {oldest_key}")
            await self._discard(runner, reason=f"evict_lru session={oldest_key}")
        elif self._generic_pool:
            runner, _ = self._generic_pool.popleft()
            self._evictions += 1
            logger.debug("LRU evict (generic)")
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
        async with self._lock:
            now = time.monotonic()

            if session_id is not None:
                if session_id in self._session_pool:
                    runner, last_used = self._session_pool.pop(session_id)
                    if now - last_used <= self._idle_ttl:
                        self._hits += 1
                        logger.debug(f"Pool session hit: {session_id}")
                        return runner
                    # TTL 만료 — 폐기
                    logger.debug(f"Session runner TTL expired: {session_id}")
                    await self._discard(runner, reason=f"ttl_expired session={session_id}")

                self._misses += 1
                logger.debug(f"Pool session miss: {session_id}")

            # generic pool에서 TTL 유효한 runner 찾기
            while self._generic_pool:
                runner, idle_since = self._generic_pool.popleft()
                if now - idle_since <= self._idle_ttl:
                    logger.debug("Pool generic hit")
                    return runner
                # TTL 만료 — 폐기
                logger.debug("Generic runner TTL expired, discarding")
                await self._discard(runner, reason="ttl_expired generic")

            # 새 runner 생성 — idle pool이 가득 찼으면 LRU 퇴거
            if self._total_size() >= self._max_size:
                await self._evict_lru_unlocked()

            runner = self._make_runner()
            logger.debug("Pool: new runner created")
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
                logger.debug(f"Pool: runner released to session pool: {session_id}")
            else:
                self._generic_pool.append((runner, now))
                logger.debug("Pool: runner released to generic pool")

    async def evict_lru(self) -> None:
        """가장 오래 사용되지 않은 runner를 disconnect & 제거 (공개 API)"""
        async with self._lock:
            await self._evict_lru_unlocked()

    async def shutdown(self) -> int:
        """모든 runner disconnect

        Returns:
            종료된 runner 수
        """
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
