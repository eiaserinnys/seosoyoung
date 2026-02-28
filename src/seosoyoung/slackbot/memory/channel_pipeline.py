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
from typing import Callable, Optional

from seosoyoung.slackbot.memory.channel_intervention import (
    InterventionAction,
    InterventionHistory,
    burst_intervention_probability,
    execute_interventions,
    intervention_probability,
    send_debug_log,
    send_intervention_probability_debug_log,
    send_multi_judge_debug_log,
)
from seosoyoung.slackbot.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
    JudgeItem,
    JudgeResult,
)
from seosoyoung.slackbot.memory.channel_prompts import (
    build_channel_intervene_user_prompt,
    get_channel_intervene_system_prompt,
)
from seosoyoung.slackbot.memory.channel_store import ChannelStore
from seosoyoung.slackbot.memory.token_counter import TokenCounter

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


def _apply_importance_modifiers(
    judge_result: JudgeResult,
    pending_messages: list[dict],
) -> None:
    """related_to_me 가중치와 addressed_to_me 강제 반응을 적용합니다.

    - related_to_me == True → importance × 2 (상한 10)
    - addressed_to_me == True && 발신자가 사람 → importance 최소 7, intervene 전환
    """
    msg_by_ts: dict[str, dict] = {}
    for msg in pending_messages:
        ts = msg.get("ts", "")
        if ts:
            msg_by_ts[ts] = msg

    for item in judge_result.items:
        # related_to_me 가중치
        if item.related_to_me:
            item.importance = min(item.importance * 2, 10)

        # addressed_to_me 강제 반응: 발신자가 사람(bot_id 없음)일 때
        if item.addressed_to_me:
            orig_msg = msg_by_ts.get(item.ts, {})
            is_bot = bool(orig_msg.get("bot_id"))
            if not is_bot:
                item.importance = max(item.importance, 7)
                if item.reaction_type != "intervene":
                    item.reaction_type = "intervene"
                    item.reaction_target = item.reaction_target or item.ts
                    if not item.reaction_content:
                        item.reaction_content = "(addressed)"


def _validate_linked_messages(
    judge_result: JudgeResult,
    judged_messages: list[dict],
    pending_messages: list[dict],
    thread_buffers: dict[str, list[dict]] | None = None,
) -> None:
    """linked_message_ts가 실제 존재하는 ts인지 검증하고, 환각된 ts를 제거합니다.

    자기 자신을 가리키는 링크도 제거합니다.
    """
    known_ts: set[str] = set()
    for msg in judged_messages:
        ts = msg.get("ts", "")
        if ts:
            known_ts.add(ts)
    for msg in pending_messages:
        ts = msg.get("ts", "")
        if ts:
            known_ts.add(ts)
    # Bug B: thread_buffers 메시지 ts도 known_ts에 포함
    if thread_buffers:
        for msgs in thread_buffers.values():
            for msg in msgs:
                ts = msg.get("ts", "")
                if ts:
                    known_ts.add(ts)

    for item in judge_result.items:
        if item.linked_message_ts is None:
            continue
        # 자기 자신을 가리키거나 존재하지 않는 ts → 제거
        if item.linked_message_ts == item.ts or item.linked_message_ts not in known_ts:
            logger.debug(
                f"linked_message_ts 환각 제거: {item.ts} → {item.linked_message_ts}"
            )
            item.linked_message_ts = None
            item.link_reason = None


def _get_max_importance_item(judge_result: JudgeResult) -> JudgeItem | None:
    """JudgeResult에서 가장 높은 중요도의 JudgeItem을 반환합니다."""
    if not judge_result.items:
        return None
    return max(judge_result.items, key=lambda item: item.importance)


def _filter_already_reacted(
    actions: list[InterventionAction],
    pending_messages: list[dict],
    bot_user_id: str | None,
) -> list[InterventionAction]:
    """봇이 이미 리액션한 메시지에 대한 react 액션을 필터링합니다.

    pending_messages의 reactions 필드에 봇이 같은 이모지로 이미 리액션한 경우 스킵합니다.

    Args:
        actions: react 타입 InterventionAction 리스트
        pending_messages: pending 메시지 리스트 (reactions 필드 포함 가능)
        bot_user_id: 봇의 사용자 ID

    Returns:
        중복이 아닌 액션만 남긴 리스트
    """
    if not bot_user_id or not actions:
        return actions

    # ts → reactions 인덱스 빌드
    reactions_by_ts: dict[str, list[dict]] = {}
    for msg in pending_messages:
        ts = msg.get("ts", "")
        reactions = msg.get("reactions")
        if ts and reactions:
            reactions_by_ts[ts] = reactions

    filtered = []
    for action in actions:
        reactions = reactions_by_ts.get(action.target, [])
        already = any(
            r.get("name") == action.content and bot_user_id in r.get("users", [])
            for r in reactions
        )
        if already:
            logger.debug(
                f"react 스킵 (이미 리액션함): ts={action.target} emoji={action.content}"
            )
        else:
            filtered.append(action)
    return filtered


def _filter_mention_thread_actions(
    actions: list[InterventionAction],
    mention_handled_ts: set[str],
) -> list[InterventionAction]:
    """멘션으로 처리 중인 스레드에 대한 액션을 필터링합니다.

    멘션 스레드 메시지는 소화(consume)는 정상 처리하되,
    리액션이나 개입은 수행하지 않습니다.

    Args:
        actions: InterventionAction 리스트
        mention_handled_ts: 멘션으로 처리 중인 메시지 ts 집합

    Returns:
        멘션 스레드 대상을 제외한 액션 리스트
    """
    if not mention_handled_ts or not actions:
        return actions

    filtered = []
    for action in actions:
        if action.target in mention_handled_ts:
            logger.debug(
                f"멘션 스레드 액션 필터링: type={action.type}, target={action.target}"
            )
        else:
            filtered.append(action)
    return filtered


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
    bot_user_id: str | None = None,
    mention_tracker=None,
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

    # c) judge() 호출 — 스냅샷 시점의 pending/thread를 기록해두고,
    #    파이프라인 완료 후에는 스냅샷에 포함된 메시지만 judged로 이동합니다.
    digest_data = store.get_digest(channel_id)
    current_digest = digest_data["content"] if digest_data else None
    judged_messages = store.load_judged(channel_id)
    pending_messages = store.load_pending(channel_id)
    thread_buffers = store.load_all_thread_buffers(channel_id)

    # 스냅샷 ts 기록 — 멘션 여부와 무관하게 모든 pending을 포함
    # 멘션 스레드 메시지도 정상적으로 judged로 이동(소화)되어야 합니다.
    snapshot_ts = {m.get("ts", "") for m in pending_messages if m.get("ts")}
    snapshot_thread_ts = set(thread_buffers.keys()) if thread_buffers else None

    # 멘션 스레드 식별: 리액션/개입 필터링에 사용 (소화는 정상 처리)
    mention_handled_ts: set[str] = set()
    if mention_tracker:
        for m in pending_messages:
            thread = m.get("thread_ts", "")
            ts = m.get("ts", "")
            if mention_tracker.is_handled(thread) or mention_tracker.is_handled(ts):
                mention_handled_ts.add(ts)

        # judge에는 멘션 스레드를 제외한 pending만 전달 (토큰 절약)
        judge_pending = [
            m for m in pending_messages
            if m.get("ts", "") not in mention_handled_ts
        ]
        judge_thread_buffers = (
            {ts: msgs for ts, msgs in thread_buffers.items()
             if not mention_tracker.is_handled(ts)}
            if thread_buffers else thread_buffers
        )
        filtered_count = len(pending_messages) - len(judge_pending)
        if filtered_count > 0:
            logger.info(
                f"멘션 스레드 필터링 ({channel_id}): "
                f"judge에서 pending {filtered_count}건 제외 (소화는 정상 처리)"
            )
    else:
        judge_pending = pending_messages
        judge_thread_buffers = thread_buffers

    logger.info(
        f"리액션 판단 시작 ({channel_id}): "
        f"pending {len(judge_pending)}건 (전체 {len(pending_messages)}건), "
        f"judged {len(judged_messages)}건, "
        f"threads {len(judge_thread_buffers) if judge_thread_buffers else 0}건"
    )

    judge_result = await observer.judge(
        channel_id=channel_id,
        digest=current_digest,
        judged_messages=judged_messages,
        pending_messages=judge_pending,
        thread_buffers=judge_thread_buffers,
        bot_user_id=bot_user_id,
        slack_client=slack_client,
    )

    if judge_result is None:
        logger.warning(f"judge가 None 반환 ({channel_id})")
        return

    # d-0a) Bug D: pending ts에 없는 JudgeItem 필터링
    #   AI가 THREAD CONVERSATIONS 섹션 메시지에 대해서도 판단을 생성할 수 있음
    if judge_result.items:
        judge_pending_ts = {m.get("ts", "") for m in judge_pending if m.get("ts")}
        filtered_items = [item for item in judge_result.items if item.ts in judge_pending_ts]
        if len(filtered_items) < len(judge_result.items):
            removed = len(judge_result.items) - len(filtered_items)
            logger.info(
                f"non-pending JudgeItem {removed}건 필터링 ({channel_id}): "
                f"judge_pending_ts={len(judge_pending_ts)}건"
            )
        judge_result.items = filtered_items

    # d-0b) linked_message_ts 환각 검증
    _validate_linked_messages(judge_result, judged_messages, judge_pending, judge_thread_buffers)

    # d-0c) 가중치 적용: related_to_me, addressed_to_me 강제 반응
    _apply_importance_modifiers(judge_result, judge_pending)

    # d) 리액션 처리
    # e) 스냅샷 메시지는 예외 발생 여부와 무관하게 반드시 judged로 이동해야 함
    #    (이동하지 않으면 pending에 영원히 남아 중복 응답 발생 — Bug A)
    try:
        if judge_result.items:
            # 복수 판단 경로
            await _handle_multi_judge(
                judge_result=judge_result,
                store=store,
                channel_id=channel_id,
                slack_client=slack_client,
                cooldown=cooldown,
                pending_messages=judge_pending,
                current_digest=current_digest,
                debug_channel=debug_channel,
                intervention_threshold=intervention_threshold,
                llm_call=llm_call,
                bot_user_id=bot_user_id,
                session_manager=kwargs.get("session_manager"),
                thread_buffers=judge_thread_buffers,
                mention_handled_ts=mention_handled_ts,
            )
        else:
            # 하위호환: 단일 판단 경로
            await _handle_single_judge(
                judge_result=judge_result,
                store=store,
                channel_id=channel_id,
                slack_client=slack_client,
                cooldown=cooldown,
                pending_messages=judge_pending,
                current_digest=current_digest,
                debug_channel=debug_channel,
                intervention_threshold=intervention_threshold,
                llm_call=llm_call,
                bot_user_id=bot_user_id,
                session_manager=kwargs.get("session_manager"),
                thread_buffers=judge_thread_buffers,
                mention_handled_ts=mention_handled_ts,
            )
    finally:
        # 스냅샷에 포함된 메시지만 judged로 이동 (파이프라인 중 새로 도착한 메시지는 pending에 잔류)
        store.move_snapshot_to_judged(channel_id, snapshot_ts, snapshot_thread_ts)


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
    bot_user_id: str | None = None,
    session_manager=None,
    thread_buffers: dict[str, list[dict]] | None = None,
    mention_handled_ts: set[str] | None = None,
) -> None:
    """복수 JudgeItem 처리: 이모지 일괄 + 개입 확률 판단"""
    actions = _parse_judge_actions(judge_result)

    # 멘션 스레드 대상 액션 필터링 (소화는 정상 처리, 리액션/개입만 제외)
    actions = _filter_mention_thread_actions(actions, mention_handled_ts or set())

    react_actions = [a for a in actions if a.type == "react"]
    message_actions = [a for a in actions if a.type == "message"]

    # 봇이 이미 리액션한 메시지 필터링
    react_actions = _filter_already_reacted(
        react_actions, pending_messages, bot_user_id,
    )

    # 이모지 리액션 일괄 실행
    if react_actions:
        await execute_interventions(slack_client, channel_id, react_actions)

    # 개입 처리 (burst/cooldown 확률 기반)
    executed_messages: list[InterventionAction] = []
    if message_actions:
        # 개입에 사용할 importance는 가장 높은 item의 것
        max_item = _get_max_importance_item(judge_result)
        importance_for_prob = max_item.importance if max_item else 5

        prob = cooldown.burst_probability(channel_id, importance_for_prob)

        # burst 진행 중 여부에 따라 판정 분기
        mins_since = cooldown.minutes_since_last(channel_id)
        BURST_GAP = 5  # burst_intervention_probability와 동일한 상수
        if mins_since <= BURST_GAP:
            # burst 내에서는 prob 자체가 판정 기준
            final_score = prob
            passed = final_score >= 0.35
            # 디버그 호환: burst 내에서는 time/freq를 burst 정보로 대체
            time_factor = prob
            freq_factor = 1.0
        else:
            # cooldown 구간에서는 importance 가중
            final_score = (importance_for_prob / 10.0) * prob
            passed = final_score >= intervention_threshold
            time_factor = prob
            freq_factor = importance_for_prob / 10.0

        send_intervention_probability_debug_log(
            client=slack_client,
            debug_channel=debug_channel,
            source_channel=channel_id,
            importance=importance_for_prob,
            time_factor=time_factor,
            freq_factor=freq_factor,
            probability=prob,
            final_score=final_score,
            threshold=0.35 if mins_since <= BURST_GAP else intervention_threshold,
            passed=passed,
        )

        if passed:
            # 개입은 1건만 (가장 중요한 것)
            # message_actions는 이미 멘션 필터를 거쳤으므로,
            # 필터된 target 집합에 속하는 항목만 선택합니다.
            filtered_targets = {a.target for a in message_actions}
            intervene_item = None
            for item in judge_result.items:
                if item.reaction_type == "intervene" and item.reaction_target in filtered_targets:
                    if intervene_item is None or item.importance > intervene_item.importance:
                        intervene_item = item

            if intervene_item:
                action = _parse_judge_item_action(intervene_item)
                if action:
                    if llm_call:
                        await _execute_intervene(
                            store=store,
                            channel_id=channel_id,
                            slack_client=slack_client,
                            action=action,
                            pending_messages=pending_messages,
                            observer_reason=intervene_item.reaction_content,
                            llm_call=llm_call,
                            bot_user_id=bot_user_id,
                            session_manager=session_manager,
                            thread_buffers=thread_buffers,
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
        slack_client=slack_client,
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
    bot_user_id: str | None = None,
    session_manager=None,
    thread_buffers: dict[str, list[dict]] | None = None,
    mention_handled_ts: set[str] | None = None,
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
    # 멘션 스레드 대상 액션 필터링 (소화는 정상 처리, 리액션/개입만 제외)
    actions = _filter_mention_thread_actions(actions, mention_handled_ts or set())
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

        # 봇이 이미 리액션한 메시지 필터링
        react_actions = _filter_already_reacted(
            react_actions, pending_messages, bot_user_id,
        )

        if react_actions:
            await execute_interventions(slack_client, channel_id, react_actions)

        executed_messages: list[InterventionAction] = []
        if message_actions:
            prob = cooldown.burst_probability(channel_id, judge_result.importance)

            # burst 진행 중 여부에 따라 판정 분기
            mins_since = cooldown.minutes_since_last(channel_id)
            BURST_GAP = 5  # burst_intervention_probability와 동일한 상수
            if mins_since <= BURST_GAP:
                final_score = prob
                passed = final_score >= 0.35
                time_factor = prob
                freq_factor = 1.0
            else:
                final_score = (judge_result.importance / 10.0) * prob
                passed = final_score >= intervention_threshold
                time_factor = prob
                freq_factor = judge_result.importance / 10.0

            send_intervention_probability_debug_log(
                client=slack_client,
                debug_channel=debug_channel,
                source_channel=channel_id,
                importance=judge_result.importance,
                time_factor=time_factor,
                freq_factor=freq_factor,
                probability=prob,
                final_score=final_score,
                threshold=0.35 if mins_since <= BURST_GAP else intervention_threshold,
                passed=passed,
            )

            if passed:
                if llm_call:
                    for action in message_actions:
                        await _execute_intervene(
                            store=store,
                            channel_id=channel_id,
                            slack_client=slack_client,
                            action=action,
                            pending_messages=pending_messages,
                            observer_reason=judge_result.reaction_content,
                            llm_call=llm_call,
                            bot_user_id=bot_user_id,
                            session_manager=session_manager,
                            thread_buffers=thread_buffers,
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
    llm_call: Optional[Callable] = None,
    bot_user_id: str | None = None,
    session_manager=None,
    thread_buffers: dict[str, list[dict]] | None = None,
) -> None:
    """서소영의 개입 응답을 생성하고 발송합니다."""
    # 0. 트리거 메시지에 :ssy-thinking: 이모지 추가 (응답 생성 중 피드백)
    reaction_ts = action.target if action.target and action.target != "channel" else None
    if reaction_ts:
        try:
            slack_client.reactions_add(
                channel=channel_id, timestamp=reaction_ts, name="ssy-thinking",
            )
        except Exception as e:
            logger.debug(f"ssy-thinking 이모지 추가 실패: {e}")

    # 1. 갱신된 digest 로드
    digest_data = store.get_digest(channel_id)
    digest = digest_data["content"] if digest_data else None

    # 2. 트리거 메시지와 최근 메시지 분리
    target_ts = action.target
    trigger_message = None
    recent_messages = []

    if target_ts and target_ts != "channel":
        # pending에서 먼저 검색
        for i, msg in enumerate(pending_messages):
            if msg.get("ts") == target_ts:
                trigger_message = msg
                start = max(0, i - 5)
                recent_messages = pending_messages[start:i]
                break

        # Bug C: pending에 없으면 thread_buffers에서 검색
        if trigger_message is None and thread_buffers:
            for thread_msgs in thread_buffers.values():
                for msg in thread_msgs:
                    if msg.get("ts") == target_ts:
                        trigger_message = msg
                        recent_messages = pending_messages[-5:]
                        break
                if trigger_message is not None:
                    break

        # Bug C: thread_buffers에도 없으면 judged에서 검색
        if trigger_message is None:
            judged_messages = store.load_judged(channel_id)
            for msg in judged_messages:
                if msg.get("ts") == target_ts:
                    trigger_message = msg
                    recent_messages = pending_messages[-5:]
                    break

        # Bug C: 어디에서도 못 찾으면 intervention 스킵 (엉뚱한 메시지 폴백 방지)
        if trigger_message is None:
            logger.warning(
                f"intervene 스킵: target_ts={target_ts}를 "
                f"pending/thread_buffers/judged 어디에서도 찾을 수 없음 ({channel_id})"
            )
            _remove_thinking_reaction(slack_client, channel_id, reaction_ts)
            return

    if trigger_message is None and pending_messages:
        # target이 "channel"인 경우에만 여기에 도달
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
        slack_client=slack_client,
        thread_buffers=thread_buffers,
    )

    # 4. 응답 생성
    try:
        if llm_call:
            response_text = await llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            logger.warning(f"intervene: llm_call이 없음 ({channel_id})")
            _remove_thinking_reaction(slack_client, channel_id, reaction_ts)
            return
    except Exception as e:
        logger.error(f"intervene 응답 생성 실패 ({channel_id}): {e}")
        _remove_thinking_reaction(slack_client, channel_id, reaction_ts)
        return

    if not response_text or not response_text.strip():
        logger.warning(f"intervene 빈 응답 ({channel_id})")
        _remove_thinking_reaction(slack_client, channel_id, reaction_ts)
        return

    # 5. 슬랙 발송 + 봇 응답 ts를 judged에 기록
    try:
        if action.target == "channel":
            resp = slack_client.chat_postMessage(
                channel=channel_id,
                text=response_text.strip(),
            )
        else:
            resp = slack_client.chat_postMessage(
                channel=channel_id,
                text=response_text.strip(),
                thread_ts=action.target,
            )

        # 봇 응답을 judged에 기록하여 후속 judge에서 맥락으로 사용
        resp_ts = None
        if isinstance(resp, dict):
            resp_ts = resp.get("ts")
        elif hasattr(resp, "data"):
            resp_ts = resp.data.get("ts")

        if resp_ts:
            bot_msg = {
                "ts": resp_ts,
                "user": bot_user_id or "bot",
                "text": response_text.strip(),
            }
            store.append_judged(channel_id, [bot_msg])
            logger.info(f"봇 응답 judged 기록 ({channel_id}): ts={resp_ts}")

            # 스레드 대상 개입이면 세션 생성 (후속 멘션 대화 대비)
            if session_manager and action.target != "channel":
                try:
                    session_manager.create(
                        thread_ts=resp_ts,
                        channel_id=channel_id,
                        source_type="hybrid",
                    )
                    logger.info(f"개입 세션 생성 ({channel_id}): ts={resp_ts}")
                except Exception as e:
                    logger.error(f"개입 세션 생성 실패 ({channel_id}): {e}")

        # 발송 성공: :ssy-thinking: → :ssy-happy: 교체
        _swap_thinking_to_happy(slack_client, channel_id, reaction_ts)

    except Exception as e:
        logger.error(f"intervene 슬랙 발송 실패 ({channel_id}): {e}")
        _remove_thinking_reaction(slack_client, channel_id, reaction_ts)


def _remove_thinking_reaction(client, channel_id: str, ts: str | None) -> None:
    """트리거 메시지에서 :ssy-thinking: 이모지를 제거합니다."""
    if not ts:
        return
    try:
        client.reactions_remove(channel=channel_id, timestamp=ts, name="ssy-thinking")
    except Exception:
        pass


def _swap_thinking_to_happy(client, channel_id: str, ts: str | None) -> None:
    """:ssy-thinking: 이모지를 :ssy-happy:로 교체합니다."""
    if not ts:
        return
    try:
        client.reactions_remove(channel=channel_id, timestamp=ts, name="ssy-thinking")
    except Exception:
        pass
    try:
        client.reactions_add(channel=channel_id, timestamp=ts, name="ssy-happy")
    except Exception as e:
        logger.debug(f"ssy-happy 이모지 추가 실패: {e}")
