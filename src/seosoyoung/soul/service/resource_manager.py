"""
ResourceManager - 동시 실행 제한 관리

Claude Code 동시 실행 수를 제한하고 리소스를 관리합니다.
"""

import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager


# 기본 최대 동시 세션 수
DEFAULT_MAX_CONCURRENT = 3


class ResourceManager:
    """
    동시 실행 제한 관리자

    역할:
    1. 전역 동시 실행 제한 (Semaphore)
    2. 시스템 메모리 모니터링
    3. 리소스 획득/해제 컨텍스트 매니저 제공
    """

    def __init__(self, max_concurrent: Optional[int] = None):
        """
        Args:
            max_concurrent: 최대 동시 세션 수 (기본값: 환경변수 또는 3)
        """
        self._max_concurrent = max_concurrent or int(
            os.getenv("MAX_CONCURRENT_SESSIONS", str(DEFAULT_MAX_CONCURRENT))
        )
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._active_count = 0
        self._lock = asyncio.Lock()

    @property
    def max_concurrent(self) -> int:
        """최대 동시 세션 수"""
        return self._max_concurrent

    @property
    def active_count(self) -> int:
        """현재 활성 세션 수"""
        return self._active_count

    @property
    def available_slots(self) -> int:
        """사용 가능한 슬롯 수"""
        return self._max_concurrent - self._active_count

    def can_acquire(self) -> bool:
        """
        리소스 획득 가능 여부 (non-blocking check)

        Returns:
            True if slot available, False otherwise
        """
        return self._active_count < self._max_concurrent

    @asynccontextmanager
    async def acquire(self, timeout: Optional[float] = None):
        """
        리소스 획득 컨텍스트 매니저

        Args:
            timeout: 대기 타임아웃 (초). None이면 무한 대기

        Raises:
            asyncio.TimeoutError: 타임아웃 초과
            RuntimeError: 동시 실행 제한 초과 (non-blocking 모드)

        Usage:
            async with resource_manager.acquire():
                # Claude Code 실행
                pass
        """
        acquired = False
        try:
            if timeout is not None:
                # 타임아웃 있는 경우
                try:
                    await asyncio.wait_for(
                        self._semaphore.acquire(),
                        timeout=timeout
                    )
                    acquired = True
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        f"동시 실행 제한 초과 (max={self._max_concurrent})"
                    )
            else:
                # 무한 대기
                await self._semaphore.acquire()
                acquired = True

            async with self._lock:
                self._active_count += 1

            yield

        finally:
            if acquired:
                async with self._lock:
                    self._active_count -= 1
                self._semaphore.release()

    def try_acquire(self) -> bool:
        """
        리소스 획득 시도 (non-blocking, 동기 버전)

        Returns:
            True if acquired, False if not available
        """
        if self._active_count < self._max_concurrent:
            self._active_count += 1
            return True
        return False

    def release(self) -> None:
        """리소스 해제 (try_acquire와 쌍으로 사용)"""
        try:
            self._semaphore.release()
            self._active_count = max(0, self._active_count - 1)
        except ValueError:
            pass  # 이미 해제됨

    def get_stats(self) -> dict:
        """리소스 통계 반환"""
        return {
            "active_sessions": self._active_count,
            "max_concurrent": self._max_concurrent,
            "available_slots": self.available_slots,
        }


# 싱글톤 인스턴스
resource_manager = ResourceManager()
