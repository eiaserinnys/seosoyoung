"""채널 소화/판단 파이프라인

pending 버퍼에 쌓인 메시지를 기반으로:
1. pending 토큰 확인 → threshold_A 미만이면 스킵
2. judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 digest에 편입)
3. judge() 호출 (digest + judged + pending → 리액션 판단)
4. 리액션 처리 (슬랙 발송)
5. pending을 judged로 이동
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from seosoyoung.memory.channel_intervention import (
    CooldownManager,
    InterventionAction,
    execute_interventions,
    send_debug_log,
    send_intervention_mode_debug_log,
)
from seosoyoung.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
    JudgeResult,
)
from seosoyoung.memory.channel_prompts import (
    build_channel_intervene_user_prompt,
    build_intervention_mode_prompt,
    get_channel_intervene_system_prompt,
    get_intervention_mode_system_prompt,
)
from seosoyoung.memory.channel_store import ChannelStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


def _judge_result_to_observer_result(
    judge: JudgeResult, digest: str = "",
) -> ChannelObserverResult:
    """JudgeResult를 ChannelObserverResult로 변환 (하위호환 인터페이스용)"""
    return ChannelObserverResult(
        digest=digest,
        importance=judge.importance,
        reaction_type=judge.reaction_type,
        reaction_target=judge.reaction_target,
        reaction_content=judge.reaction_content,
    )


def _parse_judge_actions(judge_result: JudgeResult) -> list[InterventionAction]:
    """JudgeResult에서 InterventionAction 리스트를 생성합니다."""
    if judge_result.reaction_type == "none":
        return []

    if judge_result.reaction_type == "react":
        return [InterventionAction(
            type="react",
            target=judge_result.reaction_target,
            content=judge_result.reaction_content,
        )]

    if judge_result.reaction_type == "intervene":
        return [InterventionAction(
            type="message",
            target=judge_result.reaction_target,
            content=judge_result.reaction_content,
        )]

    return []


async def run_channel_pipeline(
    store: ChannelStore,
    observer: ChannelObserver,
    channel_id: str,
    slack_client,
    cooldown: CooldownManager,
    threshold_a: int = 150,
    threshold_b: int = 5000,
    compressor: Optional[DigestCompressor] = None,
    digest_max_tokens: int = 10_000,
    digest_target_tokens: int = 5_000,
    debug_channel: str = "",
    max_intervention_turns: int = 0,
    llm_call: Optional[Callable] = None,
) -> None:
    """소화/판단 분리 파이프라인을 실행합니다.

    흐름:
    a) pending 토큰 확인 → threshold_A 미만이면 스킵
    b) judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 편입)
    c) judge() 호출 (digest + judged + pending)
    d) 리액션 처리 (기존 intervention 로직 재활용)
    e) pending을 judged로 이동

    Args:
        store: 채널 데이터 저장소
        observer: ChannelObserver 인스턴스
        channel_id: 대상 채널
        slack_client: Slack WebClient
        cooldown: CooldownManager 인스턴스
        threshold_a: pending 판단 트리거 토큰 임계치
        threshold_b: digest 편입 트리거 토큰 임계치
        compressor: DigestCompressor (None이면 압축 건너뜀)
        digest_max_tokens: digest 압축 트리거 토큰 임계치
        digest_target_tokens: digest 압축 목표 토큰
        debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
        max_intervention_turns: 개입 모드 최대 턴 (0이면 개입 모드 비활성)
        llm_call: async callable(system_prompt, user_prompt) -> str
    """
    token_counter = TokenCounter()

    # a) pending 토큰 확인
    pending_tokens = store.count_pending_tokens(channel_id)
    if pending_tokens < threshold_a:
        logger.debug(
            f"파이프라인 스킵 ({channel_id}): "
            f"pending {pending_tokens} tok < threshold_A {threshold_a}"
        )
        return

    # b) judged + pending 합산 > threshold_B이면 → digest 편입
    judged_plus_pending = store.count_judged_plus_pending_tokens(channel_id)
    if judged_plus_pending > threshold_b:
        judged_messages = store.load_judged(channel_id)
        if judged_messages:
            digest_data = store.get_digest(channel_id)
            existing_digest = digest_data["content"] if digest_data else None

            logger.info(
                f"digest 편입 시작 ({channel_id}): "
                f"judged+pending {judged_plus_pending} tok > threshold_B {threshold_b}"
            )

            digest_result = await observer.digest(
                channel_id=channel_id,
                existing_digest=existing_digest,
                judged_messages=judged_messages,
            )

            if digest_result:
                store.save_digest(
                    channel_id,
                    content=digest_result.digest,
                    meta={
                        "token_count": digest_result.token_count,
                        "last_digested_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                store.clear_judged(channel_id)

                logger.info(
                    f"digest 편입 완료 ({channel_id}): "
                    f"digest {digest_result.token_count} tok"
                )

                # digest 압축 트리거
                if compressor and digest_result.token_count > digest_max_tokens:
                    compress_result = await compressor.compress(
                        digest=digest_result.digest,
                        target_tokens=digest_target_tokens,
                    )
                    if compress_result:
                        store.save_digest(
                            channel_id,
                            content=compress_result.digest,
                            meta={
                                "token_count": compress_result.token_count,
                                "last_digested_at": datetime.now(timezone.utc).isoformat(),
                                "last_compressed_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
            else:
                logger.warning(f"digest 편입 실패 ({channel_id})")

    # c) judge() 호출
    digest_data = store.get_digest(channel_id)
    current_digest = digest_data["content"] if digest_data else None
    judged_messages = store.load_judged(channel_id)
    pending_messages = store.load_pending(channel_id)

    logger.info(
        f"리액션 판단 시작 ({channel_id}): "
        f"pending {len(pending_messages)}건, "
        f"judged {len(judged_messages)}건"
    )

    judge_result = await observer.judge(
        channel_id=channel_id,
        digest=current_digest,
        judged_messages=judged_messages,
        pending_messages=pending_messages,
    )

    if judge_result is None:
        logger.warning(f"judge가 None 반환 ({channel_id})")
        return

    logger.info(
        f"리액션 판단 완료 ({channel_id}): "
        f"중요도 {judge_result.importance}, "
        f"반응 {judge_result.reaction_type}"
    )

    # d) 리액션 처리
    observer_result = _judge_result_to_observer_result(
        judge_result, digest=current_digest or ""
    )

    actions = _parse_judge_actions(judge_result)
    if not actions:
        await send_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            observer_result=observer_result,
            actions=[],
            actions_filtered=[],
        )
    else:
        react_actions = [a for a in actions if a.type == "react"]
        message_actions = [a for a in actions if a.type == "message"]

        if react_actions:
            await execute_interventions(slack_client, channel_id, react_actions)

        filtered_messages = cooldown.filter_actions(channel_id, message_actions)
        if filtered_messages and llm_call:
            for action in filtered_messages:
                await _execute_intervene_with_llm(
                    store=store,
                    channel_id=channel_id,
                    slack_client=slack_client,
                    llm_call=llm_call,
                    action=action,
                    pending_messages=pending_messages,
                    observer_reason=judge_result.reaction_content,
                )

            if max_intervention_turns > 0:
                cooldown.enter_intervention_mode(channel_id, max_intervention_turns)
                send_intervention_mode_debug_log(
                    client=slack_client,
                    debug_channel=debug_channel,
                    source_channel=channel_id,
                    event="enter",
                    max_turns=max_intervention_turns,
                )
            else:
                cooldown.record_intervention(channel_id)
        elif filtered_messages:
            await execute_interventions(slack_client, channel_id, filtered_messages)
            if max_intervention_turns > 0:
                cooldown.enter_intervention_mode(channel_id, max_intervention_turns)
                send_intervention_mode_debug_log(
                    client=slack_client,
                    debug_channel=debug_channel,
                    source_channel=channel_id,
                    event="enter",
                    max_turns=max_intervention_turns,
                )
            else:
                cooldown.record_intervention(channel_id)

        filtered = react_actions + filtered_messages

        await send_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            observer_result=observer_result,
            actions=actions,
            actions_filtered=filtered,
        )

    # e) pending을 judged로 이동
    store.move_pending_to_judged(channel_id)


async def _execute_intervene_with_llm(
    store: ChannelStore,
    channel_id: str,
    slack_client,
    llm_call: Callable,
    action: InterventionAction,
    pending_messages: list[dict],
    observer_reason: str | None = None,
) -> None:
    """LLM을 호출하여 서소영의 개입 응답을 생성하고 발송합니다.

    Args:
        store: 채널 데이터 저장소
        channel_id: 대상 채널
        slack_client: Slack WebClient
        llm_call: async callable(system_prompt, user_prompt) -> str
        action: 실행할 InterventionAction (type="message")
        pending_messages: pending 메시지 (트리거/컨텍스트 분리용)
        observer_reason: judge의 reaction_content (판단 근거/초안)
    """
    # 1. 갱신된 digest 로드
    digest_data = store.get_digest(channel_id)
    digest = digest_data["content"] if digest_data else None

    # 2. 트리거 메시지와 최근 메시지 분리
    target_ts = action.target
    trigger_message = None
    recent_messages = []

    if target_ts and target_ts != "channel":
        for i, msg in enumerate(pending_messages):
            if msg.get("ts") == target_ts:
                trigger_message = msg
                start = max(0, i - 5)
                recent_messages = pending_messages[start:i]
                break

    if trigger_message is None and pending_messages:
        trigger_message = pending_messages[-1]
        recent_messages = pending_messages[-6:-1]

    # 3. 프롬프트 구성
    system_prompt = get_channel_intervene_system_prompt()
    user_prompt = build_channel_intervene_user_prompt(
        digest=digest,
        recent_messages=recent_messages,
        trigger_message=trigger_message,
        target=action.target or "channel",
        observer_reason=observer_reason,
    )

    # 4. LLM 호출
    try:
        response_text = await llm_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as e:
        logger.error(f"intervene LLM 호출 실패 ({channel_id}): {e}")
        return

    if not response_text or not response_text.strip():
        logger.warning(f"intervene LLM 빈 응답 ({channel_id})")
        return

    # 5. 슬랙 발송
    try:
        if action.target == "channel":
            slack_client.chat_postMessage(
                channel=channel_id,
                text=response_text.strip(),
            )
        else:
            slack_client.chat_postMessage(
                channel=channel_id,
                text=response_text.strip(),
                thread_ts=action.target,
            )
    except Exception as e:
        logger.error(f"intervene 슬랙 발송 실패 ({channel_id}): {e}")


async def respond_in_intervention_mode(
    store: ChannelStore,
    channel_id: str,
    slack_client,
    cooldown: CooldownManager,
    llm_call: Callable,
    debug_channel: str = "",
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
        debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
    """
    # 1. pending 버퍼 로드
    messages = store.load_pending(channel_id)
    if not messages:
        return

    # 2. 다이제스트 로드
    digest_data = store.get_digest(channel_id)
    digest = digest_data["content"] if digest_data else None

    # 3. 프롬프트 구성
    remaining = cooldown.get_remaining_turns(channel_id)
    system_prompt = get_intervention_mode_system_prompt()
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
        send_intervention_mode_debug_log(
            client=slack_client, debug_channel=debug_channel,
            source_channel=channel_id, event="error",
            error=f"LLM 호출 실패: {e}",
        )
        return

    if not response_text or not response_text.strip():
        logger.warning(f"개입 모드 LLM 빈 응답 ({channel_id})")
        send_intervention_mode_debug_log(
            client=slack_client, debug_channel=debug_channel,
            source_channel=channel_id, event="error",
            error="LLM 빈 응답",
        )
        return

    # 5. 슬랙 발송
    try:
        slack_client.chat_postMessage(
            channel=channel_id,
            text=response_text.strip(),
        )
    except Exception as e:
        logger.error(f"개입 모드 슬랙 발송 실패 ({channel_id}): {e}")
        send_intervention_mode_debug_log(
            client=slack_client, debug_channel=debug_channel,
            source_channel=channel_id, event="error",
            error=f"슬랙 발송 실패: {e}",
        )
        return

    # 6. 버퍼 비우기 + 턴 소모
    store.clear_buffers(channel_id)
    new_remaining = cooldown.consume_turn(channel_id)

    # 7. 디버그 로그
    send_intervention_mode_debug_log(
        client=slack_client, debug_channel=debug_channel,
        source_channel=channel_id, event="respond",
        remaining_turns=new_remaining,
        response_text=response_text.strip(),
        new_messages=messages,
    )

    # 턴 소진 시 종료 로그
    if new_remaining == 0:
        send_intervention_mode_debug_log(
            client=slack_client, debug_channel=debug_channel,
            source_channel=channel_id, event="exit",
        )
