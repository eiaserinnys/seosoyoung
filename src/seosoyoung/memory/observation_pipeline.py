"""관찰 파이프라인

세션 종료 시 대화를 관찰하고 관찰 로그를 갱신하는 파이프라인입니다.
agent_runner의 Stop 훅에서 비동기로 트리거됩니다.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from seosoyoung.memory.observer import Observer
from seosoyoung.memory.reflector import Reflector
from seosoyoung.memory.store import MemoryRecord, MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


def _send_debug_log(channel: str, text: str) -> None:
    """OM 디버그 로그를 슬랙 채널에 발송"""
    try:
        from seosoyoung.config import Config
        from slack_sdk import WebClient

        client = WebClient(token=Config.SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel, text=text)
    except Exception as e:
        logger.warning(f"OM 디버그 로그 발송 실패: {e}")


async def observe_conversation(
    store: MemoryStore,
    observer: Observer,
    user_id: str,
    messages: list[dict],
    min_conversation_tokens: int = 500,
    reflector: Optional[Reflector] = None,
    reflection_threshold: int = 20000,
    debug_channel: str = "",
) -> bool:
    """대화를 관찰하고 관찰 로그를 갱신합니다.

    Args:
        store: 관찰 로그 저장소
        observer: Observer 인스턴스
        user_id: 사용자 ID
        messages: 세션 대화 내역
        min_conversation_tokens: 최소 대화 토큰 수
        reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
        reflection_threshold: Reflector 트리거 토큰 임계치
        debug_channel: 디버그 로그를 발송할 슬랙 채널 (빈 문자열이면 발송 안 함)

    Returns:
        True: 관찰 성공, False: 관찰 건너뜀 또는 실패
    """
    try:
        # 기존 관찰 로그 로드
        record = store.get_record(user_id)
        existing_observations = record.observations if record else None

        if debug_channel:
            msg_count = len(messages)
            has_existing = "있음" if existing_observations else "없음"
            _send_debug_log(
                debug_channel,
                f"🔍 *OM Observer 시작*\n"
                f"• user: `{user_id}`\n"
                f"• 대화 메시지 수: {msg_count}\n"
                f"• 기존 관찰 로그: {has_existing}",
            )

        # Observer 호출
        result = await observer.observe(
            existing_observations=existing_observations,
            messages=messages,
            min_conversation_tokens=min_conversation_tokens,
        )

        if result is None:
            logger.info(f"관찰 건너뜀 (user={user_id}): 대화가 너무 짧음")
            if debug_channel:
                _send_debug_log(
                    debug_channel,
                    f"⏭️ *OM 관찰 건너뜀* (user: `{user_id}`): 대화가 너무 짧음",
                )
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

        # Reflector: 임계치 초과 시 압축
        if reflector and new_tokens > reflection_threshold:
            logger.info(
                f"Reflector 트리거 (user={user_id}): "
                f"{new_tokens} > {reflection_threshold} tokens"
            )
            if debug_channel:
                _send_debug_log(
                    debug_channel,
                    f"🗜️ *OM Reflector 트리거*\n"
                    f"• user: `{user_id}`\n"
                    f"• 현재: {new_tokens} tokens > 임계치 {reflection_threshold}",
                )
            reflection_result = await reflector.reflect(
                observations=record.observations,
                target_tokens=reflection_threshold // 2,
            )
            if reflection_result:
                record.observations = reflection_result.observations
                record.observation_tokens = reflection_result.token_count
                record.reflection_count += 1
                logger.info(
                    f"Reflector 완료 (user={user_id}): "
                    f"{new_tokens} → {reflection_result.token_count} tokens, "
                    f"총 {record.reflection_count}회 압축"
                )
                if debug_channel:
                    _send_debug_log(
                        debug_channel,
                        f"✅ *OM Reflector 완료*\n"
                        f"• {new_tokens} → {reflection_result.token_count} tokens\n"
                        f"• 총 {record.reflection_count}회 압축",
                    )

        store.save_record(record)
        logger.info(
            f"관찰 완료 (user={user_id}): "
            f"{record.observation_tokens} tokens, "
            f"총 {record.total_sessions_observed}회"
        )
        if debug_channel:
            preview = record.observations[:300]
            if len(record.observations) > 300:
                preview += "..."
            _send_debug_log(
                debug_channel,
                f"✅ *OM 관찰 완료*\n"
                f"• user: `{user_id}`\n"
                f"• {record.observation_tokens} tokens, "
                f"총 {record.total_sessions_observed}회 관찰\n"
                f"```\n{preview}\n```",
            )
        return True

    except Exception as e:
        logger.error(f"관찰 파이프라인 오류 (user={user_id}): {e}")
        if debug_channel:
            _send_debug_log(
                debug_channel,
                f"❌ *OM 관찰 파이프라인 오류*\n"
                f"• user: `{user_id}`\n"
                f"• error: `{e}`",
            )
        return False
