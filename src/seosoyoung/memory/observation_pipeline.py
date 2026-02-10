"""관찰 파이프라인

세션 종료 시 대화를 관찰하고 관찰 로그를 갱신하는 파이프라인입니다.
agent_runner의 Stop 훅에서 비동기로 트리거됩니다.
"""

import logging
from datetime import datetime, timezone

from seosoyoung.memory.observer import Observer
from seosoyoung.memory.store import MemoryRecord, MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


async def observe_conversation(
    store: MemoryStore,
    observer: Observer,
    user_id: str,
    messages: list[dict],
    min_conversation_tokens: int = 500,
) -> bool:
    """대화를 관찰하고 관찰 로그를 갱신합니다.

    Args:
        store: 관찰 로그 저장소
        observer: Observer 인스턴스
        user_id: 사용자 ID
        messages: 세션 대화 내역
        min_conversation_tokens: 최소 대화 토큰 수

    Returns:
        True: 관찰 성공, False: 관찰 건너뜀 또는 실패
    """
    try:
        # 기존 관찰 로그 로드
        record = store.get_record(user_id)
        existing_observations = record.observations if record else None

        # Observer 호출
        result = await observer.observe(
            existing_observations=existing_observations,
            messages=messages,
            min_conversation_tokens=min_conversation_tokens,
        )

        if result is None:
            logger.info(f"관찰 건너뜀 (user={user_id}): 대화가 너무 짧음")
            return False

        # 관찰 로그 갱신
        token_counter = TokenCounter()
        new_tokens = token_counter.count_string(result.observations)

        if record is None:
            record = MemoryRecord(user_id=user_id)

        record.observations = result.observations
        record.observation_tokens = new_tokens
        record.last_observed_at = datetime.now(timezone.utc)
        record.total_sessions_observed += 1

        store.save_record(record)
        logger.info(
            f"관찰 완료 (user={user_id}): "
            f"{new_tokens} tokens, "
            f"총 {record.total_sessions_observed}회"
        )
        return True

    except Exception as e:
        logger.error(f"관찰 파이프라인 오류 (user={user_id}): {e}")
        return False
