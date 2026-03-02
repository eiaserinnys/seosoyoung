"""관찰 파이프라인

매턴마다 Observer를 호출하여 세션 관찰 로그를 갱신하고, 장기 기억 후보를 수집합니다.

흐름:
1. pending 버퍼 로드 → 이번 턴 메시지와 합산 → 최소 토큰 미만이면 pending에 누적 후 스킵
2. Observer 호출 (매턴) → 세션 관찰 로그 갱신 → pending 비우기
3. candidates가 있으면 장기 기억 후보 버퍼에 적재
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축
5. 후보 버퍼 토큰 합산 → promotion 임계치 초과 시 Promoter 호출
6. 장기 기억 토큰 → compaction 임계치 초과 시 Compactor 호출
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from seosoyoung.slackbot.plugins.memory.observer import Observer
from seosoyoung.slackbot.plugins.memory.promoter import Compactor, Promoter
from seosoyoung.slackbot.plugins.memory.reflector import Reflector
from seosoyoung.slackbot.plugins.memory.store import MemoryRecord, MemoryStore
from seosoyoung.slackbot.plugins.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


def _relative_time_str(date_str: str, now: datetime) -> str:
    """날짜 문자열에 대한 상대 시간 문자열을 반환합니다."""
    try:
        obs_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        delta = now - obs_date
        days = delta.days

        if days == 0:
            return "오늘"
        elif days == 1:
            return "어제"
        elif days < 7:
            return f"{days}일 전"
        elif days < 30:
            return f"{days // 7}주 전"
        elif days < 365:
            return f"{days // 30}개월 전"
        else:
            return f"{days // 365}년 전"
    except ValueError:
        return ""


def render_observation_items(
    items: list[dict], now: datetime | None = None
) -> str:
    """관찰 항목 리스트를 사람이 읽을 수 있는 텍스트로 렌더링합니다."""
    if not items:
        return ""

    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    lines: list[str] = []
    current_date = None

    for item in items:
        session_date = item.get("session_date", "")
        if session_date != current_date:
            current_date = session_date
            relative = _relative_time_str(session_date, now) if session_date else ""
            if lines:
                lines.append("")  # 섹션 사이 빈 줄
            if relative:
                lines.append(f"## [{session_date}] ({relative})")
            elif session_date:
                lines.append(f"## [{session_date}]")
            lines.append("")

        priority = item.get("priority", "🟢")
        content = item.get("content", "")
        lines.append(f"{priority} {content}")

    return "\n".join(lines)


def render_persistent_items(items: list[dict]) -> str:
    """장기 기억 항목 리스트를 텍스트로 렌더링합니다."""
    if not items:
        return ""
    lines = []
    for item in items:
        priority = item.get("priority", "🟢")
        content = item.get("content", "")
        lines.append(f"{priority} {content}")
    return "\n".join(lines)


def _send_debug_log(
    channel: str, text: str, thread_ts: str = "", bot_token: str = ""
) -> str:
    """OM 디버그 로그를 슬랙 채널에 발송. 메시지 ts를 반환."""
    if not bot_token:
        return ""
    try:
        from slack_sdk import WebClient

        client = WebClient(token=bot_token)
        kwargs: dict = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        resp = client.chat_postMessage(**kwargs)
        return resp["ts"]
    except Exception as e:
        logger.warning(f"OM 디버그 로그 발송 실패: {e}")
        return ""


def _update_debug_log(
    channel: str, ts: str, text: str, bot_token: str = ""
) -> None:
    """기존 디버그 로그 메시지를 수정"""
    if not ts or not bot_token:
        return
    try:
        from slack_sdk import WebClient

        client = WebClient(token=bot_token)
        client.chat_update(channel=channel, ts=ts, text=text)
    except Exception as e:
        logger.warning(f"OM 디버그 로그 수정 실패: {e}")


def _format_tokens(n: int) -> str:
    """토큰 수를 천 단위 콤마 포맷"""
    return f"{n:,}"


def _blockquote(text: str, max_chars: int = 800) -> str:
    """텍스트를 슬랙 blockquote 형식으로 변환. 길면 잘라서 표시."""
    if not text or not text.strip():
        return ""
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    lines = text.split("\n")
    return "\n".join(f">{line}" for line in lines)


def _extract_new_observations(
    existing: list[dict] | None, updated: list[dict]
) -> list[dict]:
    """기존 관찰과 갱신된 관찰을 비교하여 새로 추가된 항목만 추출합니다.

    ID 기반: 기존에 없는 ID를 가진 항목을 새 항목으로 간주합니다.
    """
    if not existing:
        return updated

    existing_ids = {item.get("id") for item in existing if item.get("id")}
    new_items = []
    for item in updated:
        item_id = item.get("id")
        if not item_id or item_id not in existing_ids:
            new_items.append(item)

    return new_items


async def observe_conversation(
    store: MemoryStore,
    observer: Observer,
    thread_ts: str,
    user_id: str,
    messages: list[dict],
    min_turn_tokens: int = 200,
    reflector: Optional[Reflector] = None,
    reflection_threshold: int = 20000,
    promoter: Optional[Promoter] = None,
    promotion_threshold: int = 5000,
    compactor: Optional[Compactor] = None,
    compaction_threshold: int = 15000,
    compaction_target: int = 8000,
    debug_channel: str = "",
    anchor_ts: str = "",
    slack_bot_token: str = "",
    emoji_obs_complete: str = ":ssy-happy:",
) -> bool:
    """매턴 Observer를 호출하여 세션 관찰 로그를 갱신하고 후보를 수집합니다.

    Args:
        store: 관찰 로그 저장소
        observer: Observer 인스턴스
        thread_ts: 세션(스레드) 타임스탬프 — 저장 키
        user_id: 사용자 ID — 메타데이터용
        messages: 이번 턴 대화 내역
        min_turn_tokens: 최소 턴 토큰 (이하 스킵)
        reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
        reflection_threshold: Reflector 트리거 토큰 임계치
        promoter: Promoter 인스턴스 (None이면 승격 건너뜀)
        promotion_threshold: 후보 버퍼 → Promoter 트리거 토큰 임계치
        compactor: Compactor 인스턴스 (None이면 컴팩션 건너뜀)
        compaction_threshold: 장기 기억 → Compactor 트리거 토큰 임계치
        compaction_target: 컴팩션 목표 토큰
        debug_channel: 디버그 로그를 발송할 슬랙 채널

    Returns:
        True: 관찰 수행됨, False: 스킵 또는 실패
    """
    sid = thread_ts
    log_label = f"session={thread_ts}"
    debug_ts = ""

    # anchor_ts가 비었으면 디버그 로그를 채널 본문에 게시하게 되므로 비활성화
    if not anchor_ts:
        debug_channel = ""

    try:
        token_counter = TokenCounter()

        # 1. pending 버퍼 로드 → 이번 턴 메시지와 합산
        pending = store.load_pending_messages(thread_ts)
        if pending:
            messages = pending + messages

        turn_tokens = token_counter.count_messages(messages)

        # 최소 토큰 미달 시 pending 버퍼에 누적하고 스킵
        if turn_tokens < min_turn_tokens:
            new_messages = messages[len(pending):] if pending else messages
            if new_messages:
                store.append_pending_messages(thread_ts, new_messages)
            logger.info(
                f"관찰 스킵 ({log_label}): "
                f"{turn_tokens} tok < {min_turn_tokens} 최소"
            )
            if debug_channel:
                _send_debug_log(
                    debug_channel,
                    f":fast_forward: *OM 스킵* `{sid}`\n"
                    f">`누적 {_format_tokens(turn_tokens)} tok < {_format_tokens(min_turn_tokens)} 최소`",
                    thread_ts=anchor_ts,
                    bot_token=slack_bot_token,
                )
            return False

        # 2. 기존 관찰 로그 로드
        record = store.get_record(thread_ts)
        existing_observations = record.observations if record else None

        # 디버그 이벤트 #1: 관찰 시작 (send)
        if debug_channel:
            debug_ts = _send_debug_log(
                debug_channel,
                f":mag: *OM 관찰 시작* `{sid}`",
                thread_ts=anchor_ts,
                bot_token=slack_bot_token,
            )

        # 3. Observer 호출 (매턴)
        result = await observer.observe(
            existing_observations=existing_observations,
            messages=messages,
        )

        if result is None:
            logger.warning(f"Observer가 None을 반환 ({log_label})")
            if debug_channel:
                _update_debug_log(
                    debug_channel,
                    debug_ts,
                    f":x: *OM 관찰 오류* `{sid}`\n>`Observer returned None`",
                    bot_token=slack_bot_token,
                )
            return False

        # 4. 관찰 로그 갱신
        obs_json = json.dumps(result.observations, ensure_ascii=False)
        new_tokens = token_counter.count_string(obs_json)

        if record is None:
            record = MemoryRecord(thread_ts=thread_ts, user_id=user_id)

        record.observations = result.observations
        record.observation_tokens = new_tokens
        record.last_observed_at = datetime.now(timezone.utc)
        record.total_sessions_observed += 1

        # 5. 후보 적재
        candidate_count = 0
        candidate_summary = ""
        if result.candidates:
            store.append_candidates(thread_ts, result.candidates)
            candidate_count = len(result.candidates)
            counts: dict[str, int] = {}
            for e in result.candidates:
                p = e.get("priority", "🟢")
                counts[p] = counts.get(p, 0) + 1
            parts = []
            for emoji in ("🔴", "🟡", "🟢"):
                if emoji in counts:
                    parts.append(f"{emoji}{counts[emoji]}")
            candidate_summary = " ".join(parts)

        # 6. Reflector: 임계치 초과 시 압축
        if reflector and new_tokens > reflection_threshold:
            pre_tokens = new_tokens
            logger.info(
                f"Reflector 트리거 ({log_label}): "
                f"{new_tokens} > {reflection_threshold} tokens"
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
                    f"Reflector 완료 ({log_label}): "
                    f"{pre_tokens} → {reflection_result.token_count} tokens"
                )
                # 디버그 이벤트 #2: Reflector (별도 send)
                if debug_channel:
                    ref_text = render_observation_items(reflection_result.observations)
                    ref_quote = _blockquote(ref_text)
                    _send_debug_log(
                        debug_channel,
                        f":recycle: *OM 세션 관찰 압축* `{sid}`\n"
                        f">`{_format_tokens(pre_tokens)} → {_format_tokens(reflection_result.token_count)} tok`\n"
                        f"{ref_quote}",
                        thread_ts=anchor_ts,
                        bot_token=slack_bot_token,
                    )

        # 7. 새 관찰 diff 계산 및 저장 + pending 버퍼 비우기
        new_obs = _extract_new_observations(
            existing_observations, result.observations
        )
        store.save_new_observations(thread_ts, new_obs)
        store.save_record(record)
        store.clear_pending_messages(thread_ts)

        logger.info(
            f"관찰 완료 ({log_label}): "
            f"{record.observation_tokens} tokens, "
            f"총 {record.total_sessions_observed}회"
            + (f", 후보 +{candidate_count}" if candidate_count else "")
        )

        # 디버그 이벤트 #1 완료 (update)
        if debug_channel:
            if candidate_count:
                candidate_part = f" | 후보 +{candidate_count} ({candidate_summary})"
            else:
                candidate_part = " | 후보 없음"
            new_obs_count = len(new_obs)
            new_obs_part = (
                f" | 새 관찰 {new_obs_count}건" if new_obs_count else " | 새 관찰 없음"
            )
            _update_debug_log(
                debug_channel,
                debug_ts,
                f"{emoji_obs_complete} *OM 관찰 완료* `{sid}`\n"
                f">`{_format_tokens(turn_tokens)} tok{candidate_part}{new_obs_part}`",
                bot_token=slack_bot_token,
            )

        # 8. Promoter: 후보 버퍼 토큰 합산 → 임계치 초과 시 승격
        if promoter:
            await _try_promote(
                store=store,
                promoter=promoter,
                promotion_threshold=promotion_threshold,
                compactor=compactor,
                compaction_threshold=compaction_threshold,
                compaction_target=compaction_target,
                debug_channel=debug_channel,
                token_counter=token_counter,
                anchor_ts=anchor_ts,
                slack_bot_token=slack_bot_token,
                emoji_obs_complete=emoji_obs_complete,
            )

        return True

    except Exception as e:
        logger.error(f"관찰 파이프라인 오류 ({log_label}): {e}")
        if debug_channel:
            error_msg = str(e)[:200]
            _update_debug_log(
                debug_channel,
                debug_ts,
                f":x: *OM 관찰 오류* `{sid}`\n>`{error_msg}`",
                bot_token=slack_bot_token,
            )
        return False


async def _try_promote(
    store: MemoryStore,
    promoter: Promoter,
    promotion_threshold: int,
    compactor: Optional[Compactor],
    compaction_threshold: int,
    compaction_target: int,
    debug_channel: str,
    token_counter: TokenCounter,
    anchor_ts: str = "",
    slack_bot_token: str = "",
    emoji_obs_complete: str = ":ssy-happy:",
) -> None:
    """후보 버퍼 토큰이 임계치를 넘으면 Promoter를 호출하고, 필요 시 Compactor도 호출."""
    try:
        candidate_tokens = store.count_all_candidate_tokens()
        if candidate_tokens < promotion_threshold:
            return

        all_candidates = store.load_all_candidates()
        if not all_candidates:
            return

        # 기존 장기 기억 로드
        persistent_data = store.get_persistent()
        existing_persistent = persistent_data["content"] if persistent_data else []

        # 디버그 이벤트 #4: Promoter 시작 (send)
        promoter_debug_ts = ""
        if debug_channel:
            promoter_debug_ts = _send_debug_log(
                debug_channel,
                f":brain: *LTM 승격 검토 시작*\n"
                f">`후보 {_format_tokens(candidate_tokens)} tok ({len(all_candidates)}건)`",
                thread_ts=anchor_ts,
                bot_token=slack_bot_token,
            )

        logger.info(
            f"Promoter 트리거: {candidate_tokens} tok ({len(all_candidates)}건)"
        )

        result = await promoter.promote(
            candidates=all_candidates,
            existing_persistent=existing_persistent,
        )

        # 승격된 항목이 있으면 장기 기억에 머지
        if result.promoted:
            merged = Promoter.merge_promoted(existing_persistent, result.promoted)
            persistent_json = json.dumps(merged, ensure_ascii=False)
            persistent_tokens = token_counter.count_string(persistent_json)

            store.save_persistent(
                content=merged,
                meta={
                    "token_count": persistent_tokens,
                    "last_promoted_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info(
                f"Promoter 완료: 승격 {result.promoted_count}건, "
                f"기각 {result.rejected_count}건, "
                f"장기기억 {persistent_tokens} tok"
            )

            # 디버그 이벤트 #5: Promoter 완료 (update #4)
            if debug_channel:
                priority_parts = []
                for emoji in ("🔴", "🟡", "🟢"):
                    cnt = result.priority_counts.get(emoji, 0)
                    if cnt:
                        priority_parts.append(f"{emoji}{cnt}")
                priority_str = " ".join(priority_parts)
                promoted_text = render_persistent_items(result.promoted)
                promoted_quote = _blockquote(promoted_text)
                _update_debug_log(
                    debug_channel,
                    promoter_debug_ts,
                    f"{emoji_obs_complete} *LTM 승격 완료*\n"
                    f">`승격 {result.promoted_count}건 ({priority_str}) | "
                    f"기각 {result.rejected_count}건 | "
                    f"장기기억 {_format_tokens(persistent_tokens)} tok`\n"
                    f"{promoted_quote}",
                    bot_token=slack_bot_token,
                )

            # Compactor 트리거 체크
            if compactor and persistent_tokens > compaction_threshold:
                await _try_compact(
                    store=store,
                    compactor=compactor,
                    compaction_target=compaction_target,
                    persistent_tokens=persistent_tokens,
                    debug_channel=debug_channel,
                    anchor_ts=anchor_ts,
                    slack_bot_token=slack_bot_token,
                )
        else:
            logger.info(
                f"Promoter 완료: 승격 0건, 기각 {result.rejected_count}건"
            )

            # 디버그 이벤트 #5: 승격 없음 (update #4)
            if debug_channel:
                _update_debug_log(
                    debug_channel,
                    promoter_debug_ts,
                    f"{emoji_obs_complete} *LTM 승격 완료*\n"
                    f">`승격 0건 | 기각 {result.rejected_count}건`",
                    bot_token=slack_bot_token,
                )

        # 후보 버퍼 비우기
        store.clear_all_candidates()

    except Exception as e:
        logger.error(f"Promoter 파이프라인 오류: {e}")


async def _try_compact(
    store: MemoryStore,
    compactor: Compactor,
    compaction_target: int,
    persistent_tokens: int,
    debug_channel: str,
    anchor_ts: str = "",
    slack_bot_token: str = "",
) -> None:
    """장기 기억 토큰이 임계치를 넘으면 archive 후 Compactor를 호출."""
    try:
        # archive 백업
        archive_path = store.archive_persistent()
        logger.info(
            f"Compactor 트리거: {persistent_tokens} tok, archive={archive_path}"
        )

        # 장기 기억 로드
        persistent_data = store.get_persistent()
        if not persistent_data:
            return

        result = await compactor.compact(
            persistent=persistent_data["content"],
            target_tokens=compaction_target,
        )

        # 압축 결과 저장
        store.save_persistent(
            content=result.compacted,
            meta={
                "token_count": result.token_count,
                "last_compacted_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(
            f"Compactor 완료: {persistent_tokens} → {result.token_count} tok"
        )

        # 디버그 이벤트 #6: 컴팩션 (별도 send)
        if debug_channel:
            compact_text = render_persistent_items(result.compacted)
            compact_quote = _blockquote(compact_text)
            archive_info = f"\n>`archive: {archive_path}`" if archive_path else ""
            _send_debug_log(
                debug_channel,
                f":compression: *LTM 장기 기억 압축*\n"
                f">`{_format_tokens(persistent_tokens)} → {_format_tokens(result.token_count)} tok`"
                f"{archive_info}\n"
                f"{compact_quote}",
                thread_ts=anchor_ts,
                bot_token=slack_bot_token,
            )

    except Exception as e:
        logger.error(f"Compactor 파이프라인 오류: {e}")
