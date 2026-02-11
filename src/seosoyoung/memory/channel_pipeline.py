"""채널 소화 파이프라인

버퍼에 쌓인 채널 메시지를 ChannelObserver로 소화하여 digest를 갱신하고,
필요 시 DigestCompressor로 압축합니다.
소화 결과에 개입 액션이 있으면 쿨다운 필터 후 슬랙으로 발송합니다.

흐름:
1. count_buffer_tokens() 체크 → 임계치 미만이면 스킵
2. 기존 digest + 버퍼 로드
3. ChannelObserver.observe() 호출
4. 새 digest 저장 + 버퍼 비우기
5. digest 토큰이 max_tokens 초과 시 DigestCompressor 호출
6. 반응 마크업 → InterventionAction 변환 → 쿨다운 필터 → 슬랙 발송
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from seosoyoung.memory.channel_intervention import (
    CooldownManager,
    InterventionAction,
    execute_interventions,
    parse_intervention_markup,
    send_debug_log,
)
from seosoyoung.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
)
from seosoyoung.memory.channel_prompts import (
    INTERVENTION_MODE_SYSTEM_PROMPT,
    build_intervention_mode_prompt,
)
from seosoyoung.memory.channel_store import ChannelStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


async def digest_channel(
    store: ChannelStore,
    observer: ChannelObserver,
    channel_id: str,
    buffer_threshold: int = 500,
    compressor: Optional[DigestCompressor] = None,
    digest_max_tokens: int = 10_000,
    digest_target_tokens: int = 5_000,
) -> ChannelObserverResult | None:
    """채널 버퍼를 소화하여 digest를 갱신합니다.

    Args:
        store: 채널 데이터 저장소
        observer: ChannelObserver 인스턴스
        channel_id: 소화할 채널 ID
        buffer_threshold: 소화 트리거 토큰 임계치
        compressor: DigestCompressor (None이면 압축 건너뜀)
        digest_max_tokens: digest 압축 트리거 토큰 임계치
        digest_target_tokens: digest 압축 목표 토큰

    Returns:
        ChannelObserverResult (반응 정보 포함) 또는 None (스킵/실패)
    """
    token_counter = TokenCounter()

    # 1. 버퍼 토큰 체크
    buffer_tokens = store.count_buffer_tokens(channel_id)
    if buffer_tokens < buffer_threshold:
        logger.debug(
            f"채널 소화 스킵 ({channel_id}): "
            f"{buffer_tokens} tok < {buffer_threshold} 임계치"
        )
        return None

    # 2. 기존 digest + 버퍼 로드
    digest_data = store.get_digest(channel_id)
    existing_digest = digest_data["content"] if digest_data else None

    channel_messages = store.load_channel_buffer(channel_id)
    thread_buffers = store.load_all_thread_buffers(channel_id)

    logger.info(
        f"채널 소화 시작 ({channel_id}): "
        f"버퍼 {buffer_tokens} tok, "
        f"채널 메시지 {len(channel_messages)}건, "
        f"스레드 {len(thread_buffers)}건"
    )

    # 3. Observer 호출
    result = await observer.observe(
        channel_id=channel_id,
        existing_digest=existing_digest,
        channel_messages=channel_messages,
        thread_buffers=thread_buffers,
    )

    if result is None:
        logger.warning(f"ChannelObserver가 None 반환 ({channel_id})")
        return None

    # 4. digest 저장 + 버퍼 비우기
    digest_tokens = token_counter.count_string(result.digest)

    store.save_digest(
        channel_id,
        content=result.digest,
        meta={
            "token_count": digest_tokens,
            "last_importance": result.importance,
            "last_digested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    store.clear_buffers(channel_id)

    logger.info(
        f"채널 소화 완료 ({channel_id}): "
        f"digest {digest_tokens} tok, "
        f"중요도 {result.importance}, "
        f"반응 {result.reaction_type}"
    )

    # 5. digest 압축 트리거
    if compressor and digest_tokens > digest_max_tokens:
        logger.info(
            f"DigestCompressor 트리거 ({channel_id}): "
            f"{digest_tokens} > {digest_max_tokens} tok"
        )
        compress_result = await compressor.compress(
            digest=result.digest,
            target_tokens=digest_target_tokens,
        )
        if compress_result:
            store.save_digest(
                channel_id,
                content=compress_result.digest,
                meta={
                    "token_count": compress_result.token_count,
                    "last_importance": result.importance,
                    "last_digested_at": datetime.now(timezone.utc).isoformat(),
                    "last_compressed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                f"DigestCompressor 완료 ({channel_id}): "
                f"{digest_tokens} → {compress_result.token_count} tok"
            )

    return result


async def run_digest_and_intervene(
    store: ChannelStore,
    observer: ChannelObserver,
    channel_id: str,
    slack_client,
    cooldown: CooldownManager,
    buffer_threshold: int = 500,
    compressor: Optional[DigestCompressor] = None,
    digest_max_tokens: int = 10_000,
    digest_target_tokens: int = 5_000,
    debug_channel: str = "",
    max_intervention_turns: int = 0,
) -> None:
    """소화 파이프라인 + 개입 실행을 일괄 수행합니다.

    message handler에서 별도 스레드로 호출합니다.

    Args:
        store: 채널 데이터 저장소
        observer: ChannelObserver 인스턴스
        channel_id: 대상 채널
        slack_client: Slack WebClient
        cooldown: CooldownManager 인스턴스
        buffer_threshold: 소화 트리거 토큰 임계치
        compressor: DigestCompressor (None이면 압축 건너뜀)
        digest_max_tokens: digest 압축 트리거 토큰 임계치
        digest_target_tokens: digest 압축 목표 토큰
        debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
        max_intervention_turns: 개입 모드 최대 턴 (0이면 개입 모드 비활성)
    """
    # 1. 소화 파이프라인
    result = await digest_channel(
        store=store,
        observer=observer,
        channel_id=channel_id,
        buffer_threshold=buffer_threshold,
        compressor=compressor,
        digest_max_tokens=digest_max_tokens,
        digest_target_tokens=digest_target_tokens,
    )

    if result is None:
        return

    # 2. 개입 액션 파싱
    actions = parse_intervention_markup(result)
    if not actions:
        # 반응이 없어도 디버그 로그는 보냄
        await send_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            observer_result=result,
            actions=[],
            actions_filtered=[],
        )
        return

    # 3. 쿨다운 필터링
    filtered = cooldown.filter_actions(channel_id, actions)

    # 4. 슬랙 발송
    if filtered:
        await execute_interventions(slack_client, channel_id, filtered)
        # 메시지 개입이 있었으면 개입 모드 진입 (또는 쿨다운 기록)
        if any(a.type == "message" for a in filtered):
            if max_intervention_turns > 0:
                cooldown.enter_intervention_mode(channel_id, max_intervention_turns)
            else:
                cooldown.record_intervention(channel_id)

    # 5. 디버그 로그
    await send_debug_log(
        client=slack_client,
        debug_channel=debug_channel,
        source_channel=channel_id,
        observer_result=result,
        actions=actions,
        actions_filtered=filtered,
    )


async def respond_in_intervention_mode(
    store: ChannelStore,
    channel_id: str,
    slack_client,
    cooldown: CooldownManager,
    llm_call: Callable,
) -> None:
    """개입 모드 중 새 메시지에 반응합니다.

    버퍼에 쌓인 메시지를 읽고, LLM으로 서소영의 응답을 생성하여
    슬랙에 발송하고, 턴을 소모합니다.

    Args:
        store: 채널 데이터 저장소
        channel_id: 대상 채널
        slack_client: Slack WebClient
        cooldown: CooldownManager 인스턴스
        llm_call: async callable(system_prompt, user_prompt) -> str
    """
    # 1. 버퍼 로드
    messages = store.load_channel_buffer(channel_id)
    if not messages:
        return

    # 2. 다이제스트 로드
    digest_data = store.get_digest(channel_id)
    digest = digest_data["content"] if digest_data else None

    # 3. 프롬프트 구성
    remaining = cooldown.get_remaining_turns(channel_id)
    system_prompt = INTERVENTION_MODE_SYSTEM_PROMPT
    user_prompt = build_intervention_mode_prompt(
        remaining_turns=remaining,
        channel_id=channel_id,
        new_messages=messages,
        digest=digest,
    )

    # 4. LLM 호출
    try:
        response_text = await llm_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as e:
        logger.error(f"개입 모드 LLM 호출 실패 ({channel_id}): {e}")
        return

    if not response_text or not response_text.strip():
        logger.warning(f"개입 모드 LLM 빈 응답 ({channel_id})")
        return

    # 5. 슬랙 발송
    try:
        slack_client.chat_postMessage(
            channel=channel_id,
            text=response_text.strip(),
        )
    except Exception as e:
        logger.error(f"개입 모드 슬랙 발송 실패 ({channel_id}): {e}")
        return

    # 6. 버퍼 비우기 + 턴 소모
    store.clear_buffers(channel_id)
    cooldown.consume_turn(channel_id)
