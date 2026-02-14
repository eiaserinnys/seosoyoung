"""채널 소화/판단 파이프라인

pending 버퍼에 쌓인 메시지를 기반으로:
1. pending 토큰 확인 → threshold_A 미만이면 스킵
2. judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 digest에 편입)
3. judge() 호출 (digest + judged + pending → 메시지별 리액션 판단)
4. 리액션 처리 (이모지 일괄 + 확률 기반 개입 판단 + 슬랙 발송)
5. pending을 judged로 이동
"""

import logging
import math
from datetime import datetime, timezone
from typing import Callable, Optional, TYPE_CHECKING

from seosoyoung.memory.channel_intervention import (
    InterventionAction,
    InterventionHistory,
    execute_interventions,
    intervention_probability,
    send_debug_log,
    send_intervention_probability_debug_log,
    send_multi_judge_debug_log,
)
from seosoyoung.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
    JudgeItem,
    JudgeResult,
)
from seosoyoung.memory.channel_prompts import (
    build_channel_intervene_user_prompt,
    get_channel_intervene_system_prompt,
)
from seosoyoung.memory.channel_store import ChannelStore
from seosoyoung.memory.token_counter import TokenCounter

if TYPE_CHECKING:
    from seosoyoung.claude.agent_runner import ClaudeAgentRunner

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


def _parse_judge_item_action(item: JudgeItem) -> InterventionAction | None:
    """JudgeItem에서 InterventionAction을 생성합니다. 반응이 없으면 None."""
    if item.reaction_type == "none":
        return None

    if item.reaction_type == "react" and item.reaction_target and item.reaction_content:
        return InterventionAction(
            type="react",
            target=item.reaction_target,
            content=item.reaction_content,
        )

    if item.reaction_type == "intervene" and item.reaction_target and item.reaction_content:
        return InterventionAction(
            type="message",
            target=item.reaction_target,
            content=item.reaction_content,
        )

    return None


def _parse_judge_actions(judge_result: JudgeResult) -> list[InterventionAction]:
    """JudgeResult에서 InterventionAction 리스트를 생성합니다.

    items가 있으면 각 JudgeItem에서 액션을 추출합니다.
    없으면 하위호환 단일 필드에서 추출합니다.
    """
    if judge_result.items:
        actions = []
        for item in judge_result.items:
            action = _parse_judge_item_action(item)
            if action:
                actions.append(action)
        return actions

    # 하위호환: 단일 필드
    if judge_result.reaction_type == "none":
        return []

    if judge_result.reaction_type == "react" and judge_result.reaction_target:
        return [InterventionAction(
            type="react",
            target=judge_result.reaction_target,
            content=judge_result.reaction_content,
        )]

    if judge_result.reaction_type == "intervene" and judge_result.reaction_target:
        return [InterventionAction(
            type="message",
            target=judge_result.reaction_target,
            content=judge_result.reaction_content,
        )]

    return []


def _get_max_importance_item(judge_result: JudgeResult) -> JudgeItem | None:
    """JudgeResult에서 가장 높은 중요도의 JudgeItem을 반환합니다."""
    if not judge_result.items:
        return None
    return max(judge_result.items, key=lambda item: item.importance)


async def run_channel_pipeline(
    store: ChannelStore,
    observer: ChannelObserver,
    channel_id: str,
    slack_client,
    cooldown: InterventionHistory,
    threshold_a: int = 150,
    threshold_b: int = 5000,
    compressor: Optional[DigestCompressor] = None,
    digest_max_tokens: int = 10_000,
    digest_target_tokens: int = 5_000,
    debug_channel: str = "",
    intervention_threshold: float = 0.3,
    llm_call: Optional[Callable] = None,
    claude_runner: Optional["ClaudeAgentRunner"] = None,
    bot_user_id: str | None = None,
    **kwargs,
) -> None:
    """소화/판단 분리 파이프라인을 실행합니다.

    흐름:
    a) pending 토큰 확인 → threshold_A 미만이면 스킵
    b) judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 편입)
    c) judge() 호출 (digest + judged + pending → 메시지별 판단)
    d) 리액션 처리 (이모지 일괄 + 확률 기반 개입 판단 + 슬랙 발송)
    e) pending을 judged로 이동
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
    thread_buffers = store.load_all_thread_buffers(channel_id)

    logger.info(
        f"리액션 판단 시작 ({channel_id}): "
        f"pending {len(pending_messages)}건, "
        f"judged {len(judged_messages)}건, "
        f"threads {len(thread_buffers)}건"
    )

    judge_result = await observer.judge(
        channel_id=channel_id,
        digest=current_digest,
        judged_messages=judged_messages,
        pending_messages=pending_messages,
        thread_buffers=thread_buffers,
        bot_user_id=bot_user_id,
    )

    if judge_result is None:
        logger.warning(f"judge가 None 반환 ({channel_id})")
        return

    # d) 리액션 처리
    if judge_result.items:
        # 복수 판단 경로
        await _handle_multi_judge(
            judge_result=judge_result,
            store=store,
            channel_id=channel_id,
            slack_client=slack_client,
            cooldown=cooldown,
            pending_messages=pending_messages,
            current_digest=current_digest,
            debug_channel=debug_channel,
            intervention_threshold=intervention_threshold,
            llm_call=llm_call,
            claude_runner=claude_runner,
        )
    else:
        # 하위호환: 단일 판단 경로
        await _handle_single_judge(
            judge_result=judge_result,
            store=store,
            channel_id=channel_id,
            slack_client=slack_client,
            cooldown=cooldown,
            pending_messages=pending_messages,
            current_digest=current_digest,
            debug_channel=debug_channel,
            intervention_threshold=intervention_threshold,
            llm_call=llm_call,
            claude_runner=claude_runner,
        )

    # e) pending을 judged로 이동
    store.move_pending_to_judged(channel_id)


async def _handle_multi_judge(
    judge_result: JudgeResult,
    store: ChannelStore,
    channel_id: str,
    slack_client,
    cooldown: InterventionHistory,
    pending_messages: list[dict],
    current_digest: str | None,
    debug_channel: str,
    intervention_threshold: float,
    llm_call: Optional[Callable],
    claude_runner: Optional["ClaudeAgentRunner"],
) -> None:
    """복수 JudgeItem 처리: 이모지 일괄 + 개입 확률 판단"""
    actions = _parse_judge_actions(judge_result)

    react_actions = [a for a in actions if a.type == "react"]
    message_actions = [a for a in actions if a.type == "message"]

    # 이모지 리액션 일괄 실행
    if react_actions:
        await execute_interventions(slack_client, channel_id, react_actions)

    # 개입 처리 (확률 기반)
    executed_messages: list[InterventionAction] = []
    if message_actions:
        # 개입에 사용할 importance는 가장 높은 item의 것
        max_item = _get_max_importance_item(judge_result)
        importance_for_prob = max_item.importance if max_item else 5

        mins_since = cooldown.minutes_since_last(channel_id)
        recent = cooldown.recent_count(channel_id)
        prob = intervention_probability(mins_since, recent)

        time_factor = 1 - math.exp(-mins_since / 40) if mins_since != float("inf") else 1.0
        freq_factor = 1 / (1 + recent * 0.3)

        final_score = (importance_for_prob / 10.0) * prob
        passed = final_score >= intervention_threshold

        send_intervention_probability_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            importance=importance_for_prob,
            time_factor=time_factor,
            freq_factor=freq_factor,
            probability=prob,
            final_score=final_score,
            threshold=intervention_threshold,
            passed=passed,
        )

        if passed:
            # 개입은 1건만 (가장 중요한 것)
            intervene_item = None
            for item in judge_result.items:
                if item.reaction_type == "intervene":
                    if intervene_item is None or item.importance > intervene_item.importance:
                        intervene_item = item

            if intervene_item:
                action = _parse_judge_item_action(intervene_item)
                if action:
                    if claude_runner or llm_call:
                        await _execute_intervene(
                            store=store,
                            channel_id=channel_id,
                            slack_client=slack_client,
                            action=action,
                            pending_messages=pending_messages,
                            observer_reason=intervene_item.reaction_content,
                            claude_runner=claude_runner,
                            llm_call=llm_call,
                        )
                    else:
                        await execute_interventions(
                            slack_client, channel_id, [action]
                        )
                    cooldown.record(channel_id)
                    executed_messages = [action]

    # 디버그 로그: 메시지별 독립 블록
    send_multi_judge_debug_log(
        client=slack_client,
        debug_channel=debug_channel,
        source_channel=channel_id,
        items=judge_result.items,
        react_actions=react_actions,
        message_actions_executed=executed_messages,
        pending_count=len(pending_messages),
        pending_messages=pending_messages,
    )


async def _handle_single_judge(
    judge_result: JudgeResult,
    store: ChannelStore,
    channel_id: str,
    slack_client,
    cooldown: InterventionHistory,
    pending_messages: list[dict],
    current_digest: str | None,
    debug_channel: str,
    intervention_threshold: float,
    llm_call: Optional[Callable],
    claude_runner: Optional["ClaudeAgentRunner"],
) -> None:
    """하위호환: 단일 JudgeResult 처리"""
    logger.info(
        f"리액션 판단 완료 ({channel_id}): "
        f"중요도 {judge_result.importance}, "
        f"반응 {judge_result.reaction_type}"
    )

    observer_result = _judge_result_to_observer_result(
        judge_result, digest=current_digest or ""
    )

    reaction_detail = None
    if judge_result.reaction_type != "none" and judge_result.reaction_target:
        reaction_detail = (
            f"{judge_result.reaction_type}: "
            f"`{judge_result.reaction_target}` → "
            f"{judge_result.reaction_content or '(없음)'}"
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
            reasoning=judge_result.reasoning,
            emotion=judge_result.emotion,
            pending_count=len(pending_messages),
            reaction_detail=reaction_detail,
        )
    else:
        react_actions = [a for a in actions if a.type == "react"]
        message_actions = [a for a in actions if a.type == "message"]

        if react_actions:
            await execute_interventions(slack_client, channel_id, react_actions)

        executed_messages: list[InterventionAction] = []
        if message_actions:
            mins_since = cooldown.minutes_since_last(channel_id)
            recent = cooldown.recent_count(channel_id)
            prob = intervention_probability(mins_since, recent)

            time_factor = 1 - math.exp(-mins_since / 40) if mins_since != float("inf") else 1.0
            freq_factor = 1 / (1 + recent * 0.3)

            final_score = (judge_result.importance / 10.0) * prob
            passed = final_score >= intervention_threshold

            send_intervention_probability_debug_log(
                client=slack_client,
                debug_channel=debug_channel,
                source_channel=channel_id,
                importance=judge_result.importance,
                time_factor=time_factor,
                freq_factor=freq_factor,
                probability=prob,
                final_score=final_score,
                threshold=intervention_threshold,
                passed=passed,
            )

            if passed:
                if claude_runner or llm_call:
                    for action in message_actions:
                        await _execute_intervene(
                            store=store,
                            channel_id=channel_id,
                            slack_client=slack_client,
                            action=action,
                            pending_messages=pending_messages,
                            observer_reason=judge_result.reaction_content,
                            claude_runner=claude_runner,
                            llm_call=llm_call,
                        )
                else:
                    await execute_interventions(
                        slack_client, channel_id, message_actions
                    )
                cooldown.record(channel_id)
                executed_messages = message_actions

        filtered = react_actions + executed_messages

        await send_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            observer_result=observer_result,
            actions=actions,
            actions_filtered=filtered,
            reasoning=judge_result.reasoning,
            emotion=judge_result.emotion,
            pending_count=len(pending_messages),
            reaction_detail=reaction_detail,
        )


async def _execute_intervene(
    store: ChannelStore,
    channel_id: str,
    slack_client,
    action: InterventionAction,
    pending_messages: list[dict],
    observer_reason: str | None = None,
    claude_runner: Optional["ClaudeAgentRunner"] = None,
    llm_call: Optional[Callable] = None,
) -> None:
    """서소영의 개입 응답을 생성하고 발송합니다."""
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

    # 4. 응답 생성 (Claude Code SDK 우선, llm_call 폴백)
    try:
        if claude_runner:
            combined_prompt = f"{system_prompt}\n\n{user_prompt}"
            result = await claude_runner.run(prompt=combined_prompt)
            response_text = result.output if result.success else None
            if not result.success:
                logger.error(f"intervene Claude SDK 실패 ({channel_id}): {result.error}")
                return
        elif llm_call:
            response_text = await llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            logger.warning(f"intervene: claude_runner와 llm_call 모두 없음 ({channel_id})")
            return
    except Exception as e:
        logger.error(f"intervene 응답 생성 실패 ({channel_id}): {e}")
        return

    if not response_text or not response_text.strip():
        logger.warning(f"intervene 빈 응답 ({channel_id})")
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
