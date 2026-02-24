"""멘션으로 처리 중인 스레드를 추적

채널 관찰자(channel observer)가 멘션 핸들러와 동일한 메시지/스레드를
중복 처리하지 않도록, 멘션으로 이미 처리 중인 스레드의 thread_ts를
인메모리 세트로 관리합니다.
"""

import logging

logger = logging.getLogger(__name__)


class MentionTracker:
    """멘션으로 처리 중인 스레드를 추적"""

    def __init__(self):
        self._handled: set[str] = set()

    def mark(self, thread_ts: str) -> None:
        """멘션 핸들러가 처리한 스레드를 등록"""
        if thread_ts:
            self._handled.add(thread_ts)
            logger.debug(f"멘션 스레드 마킹: {thread_ts}")

    def is_handled(self, thread_ts: str) -> bool:
        """해당 스레드가 멘션으로 처리 중인지 확인"""
        return thread_ts in self._handled

    def unmark(self, thread_ts: str) -> None:
        """스레드 추적 해제"""
        self._handled.discard(thread_ts)
        logger.debug(f"멘션 스레드 해제: {thread_ts}")

    @property
    def handled_count(self) -> int:
        """현재 추적 중인 스레드 수"""
        return len(self._handled)
