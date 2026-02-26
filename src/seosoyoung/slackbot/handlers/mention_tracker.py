"""멘션으로 처리 중인 스레드를 추적

채널 관찰자(channel observer)가 멘션 핸들러와 동일한 메시지/스레드를
중복 처리하지 않도록, 멘션으로 이미 처리 중인 스레드의 thread_ts를
인메모리 딕셔너리로 관리합니다.

TTL 기반 자동 만료를 지원하여, 멘션 처리 완료 후 명시적으로
unmark()를 호출하지 않아도 일정 시간 후 자동으로 해제됩니다.
"""

import logging
import time

logger = logging.getLogger(__name__)

# 기본 TTL: 30분
DEFAULT_TTL_SECONDS = 1800


class MentionTracker:
    """멘션으로 처리 중인 스레드를 추적 (TTL 기반 자동 만료)"""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._handled: dict[str, float] = {}  # thread_ts → marked_at (monotonic)
        self._ttl_seconds = ttl_seconds

    def mark(self, thread_ts: str) -> None:
        """멘션 핸들러가 처리한 스레드를 등록"""
        if thread_ts:
            self._handled[thread_ts] = time.monotonic()
            logger.debug(f"멘션 스레드 마킹: {thread_ts}")
            self._expire()

    def is_handled(self, thread_ts: str) -> bool:
        """해당 스레드가 멘션으로 처리 중인지 확인"""
        self._expire()
        return thread_ts in self._handled

    def unmark(self, thread_ts: str) -> None:
        """스레드 추적 해제"""
        self._handled.pop(thread_ts, None)
        logger.debug(f"멘션 스레드 해제: {thread_ts}")

    @property
    def handled_count(self) -> int:
        """현재 추적 중인 스레드 수"""
        self._expire()
        return len(self._handled)

    def _expire(self) -> None:
        """TTL을 초과한 항목을 제거"""
        now = time.monotonic()
        expired = [
            ts for ts, marked_at in self._handled.items()
            if now - marked_at > self._ttl_seconds
        ]
        for ts in expired:
            del self._handled[ts]
            logger.debug(f"멘션 스레드 TTL 만료: {ts}")
