"""관찰 파이프라인

매턴마다 Observer를 호출하여 세션 관찰 로그를 갱신하고, 장기 기억 후보를 수집합니다.

흐름:
1. pending 버퍼 로드 → 이번 턴 메시지와 합산 → 최소 토큰 미만이면 pending에 누적 후 스킵
2. Observer 호출 (매턴) → 세션 관찰 로그 갱신 → pending 비우기
3. <candidates> 태그가 있으면 장기 기억 후보 버퍼에 적재
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축
5. 후보 버퍼 토큰 합산 → promotion 임계치 초과 시 Promoter 호출
6. 장기 기억 토큰 → compaction 임계치 초과 시 Compactor 호출
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from seosoyoung.config import Config
from seosoyoung.memory.observer import Observer
from seosoyoung.memory.promoter import Compactor, Promoter
from seosoyoung.memory.reflector import Reflector
from seosoyoung.memory.store import MemoryRecord, MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


def _send_debug_log(channel: str, text: str, thread_ts: str = "") -> str:
    """OM 디버그 로그를 슬랙 채널에 발송. 메시지 ts를 반환.

    Args:
        channel: 발송 채널
        text: 메시지 텍스트
        thread_ts: 스레드 앵커 ts (있으면 해당 스레드에 답글로 발송)
    """
    try:
        from seosoyoung.config import Config
        from slack_sdk import WebClient

        client = WebClient(token=Config.SLACK_BOT_TOKEN)
        kwargs: dict = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        resp = client.chat_postMessage(**kwargs)
        return resp["ts"]
    except Exception as e:
        logger.warning(f"OM 디버그 로그 발송 실패: {e}")
        return ""


def _update_debug_log(channel: str, ts: str, text: str) -> None:
    """기존 디버그 로그 메시지를 수정"""
    if not ts:
        return
    try:
        from seosoyoung.config import Config
        from slack_sdk import WebClient

        client = WebClient(token=Config.SLACK_BOT_TOKEN)
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
    existing: str | None, updated: str
) -> str:
    """기존 관찰과 갱신된 관찰을 비교하여 새로 추가된 줄만 추출합니다.

    Observer가 전체를 재작성하므로, 기존 줄 집합에 없는 줄만 반환합니다.
    """
    if not existing or not existing.strip():
        return updated

    existing_lines = set(line.strip() for line in existing.strip().splitlines() if line.strip())
    new_lines = []
    for line in updated.strip().splitlines():
        stripped = line.strip()
        if stripped and stripped not in existing_lines:
            new_lines.append(line)

    return "\n".join(new_lines) if new_lines else ""


def parse_candidate_entries(candidates_text: str) -> list[dict]:
    """<candidates> 태그 내용을 파싱하여 dict 리스트로 변환.

    각 줄에서 이모지 우선순위(🔴🟡🟢)와 내용을 추출합니다.
    """
    if not candidates_text or not candidates_text.strip():
        return []

    entries = []
    now = datetime.now(timezone.utc).isoformat()

    for line in candidates_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # 우선순위 이모지 추출
        priority = "🟢"  # 기본값
        for emoji in ("🔴", "🟡", "🟢"):
            if line.startswith(emoji):
                priority = emoji
                line = line[len(emoji):].strip()
                # "HIGH", "MEDIUM", "LOW" 접두사 제거
                line = re.sub(r"^(HIGH|MEDIUM|LOW)\s*[-–—]?\s*", "", line).strip()
                break

        if line:
            entries.append({
                "ts": now,
                "priority": priority,
                "content": line,
            })

    return entries


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

    try:
        token_counter = TokenCounter()

        # 1. pending 버퍼 로드 → 이번 턴 메시지와 합산
        pending = store.load_pending_messages(thread_ts)
        if pending:
            messages = pending + messages

        turn_tokens = token_counter.count_messages(messages)

        # 최소 토큰 미달 시 pending 버퍼에 누적하고 스킵
        if turn_tokens < min_turn_tokens:
            # 이번 턴의 새 메시지를 pending에 추가 (기존 pending은 파일에 이미 있음)
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
                )
            return False

        # 4. 관찰 로그 갱신
        new_tokens = token_counter.count_string(result.observations)

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
            entries = parse_candidate_entries(result.candidates)
            if entries:
                store.append_candidates(thread_ts, entries)
                candidate_count = len(entries)
                # 우선순위별 카운트
                counts = {}
                for e in entries:
                    p = e["priority"]
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
                    ref_quote = _blockquote(reflection_result.observations)
                    _send_debug_log(
                        debug_channel,
                        f":recycle: *OM 세션 관찰 압축* `{sid}`\n"
                        f">`{_format_tokens(pre_tokens)} → {_format_tokens(reflection_result.token_count)} tok`\n"
                        f"{ref_quote}",
                        thread_ts=anchor_ts,
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

        # 디버그 이벤트 #1 완료 (update) — 이벤트 #3 (후보 정보) 통합
        if debug_channel:
            if candidate_count:
                candidate_part = f" | 후보 +{candidate_count} ({candidate_summary})"
            else:
                candidate_part = " | 후보 없음"
            new_obs_lines = len([l for l in new_obs.splitlines() if l.strip()]) if new_obs else 0
            new_obs_part = f" | 새 관찰 {new_obs_lines}줄" if new_obs_lines else " | 새 관찰 없음"
            _update_debug_log(
                debug_channel,
                debug_ts,
                f"{Config.EMOJI_TEXT_OBS_COMPLETE} *OM 관찰 완료* `{sid}`\n"
                f">`{_format_tokens(turn_tokens)} tok{candidate_part}{new_obs_part}`",
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
        existing_persistent = persistent_data["content"] if persistent_data else ""

        # 디버그 이벤트 #4: Promoter 시작 (send)
        promoter_debug_ts = ""
        if debug_channel:
            promoter_debug_ts = _send_debug_log(
                debug_channel,
                f":brain: *LTM 승격 검토 시작*\n"
                f">`후보 {_format_tokens(candidate_tokens)} tok ({len(all_candidates)}건)`",
                thread_ts=anchor_ts,
            )

        logger.info(
            f"Promoter 트리거: {candidate_tokens} tok ({len(all_candidates)}건)"
        )

        result = await promoter.promote(
            candidates=all_candidates,
            existing_persistent=existing_persistent,
        )

        # 승격된 항목이 있으면 장기 기억에 머지
        if result.promoted and result.promoted.strip():
            merged = Promoter.merge_promoted(existing_persistent, result.promoted)
            persistent_tokens = token_counter.count_string(merged)

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

            # 디버그 이벤트 #5: Promoter 완료 — 승격 있음 (update #4)
            if debug_channel:
                priority_parts = []
                for emoji in ("🔴", "🟡", "🟢"):
                    cnt = result.priority_counts.get(emoji, 0)
                    if cnt:
                        priority_parts.append(f"{emoji}{cnt}")
                priority_str = " ".join(priority_parts)
                promoted_quote = _blockquote(result.promoted)
                _update_debug_log(
                    debug_channel,
                    promoter_debug_ts,
                    f"{Config.EMOJI_TEXT_OBS_COMPLETE} *LTM 승격 완료*\n"
                    f">`승격 {result.promoted_count}건 ({priority_str}) | "
                    f"기각 {result.rejected_count}건 | "
                    f"장기기억 {_format_tokens(persistent_tokens)} tok`\n"
                    f"{promoted_quote}",
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
                    f"{Config.EMOJI_TEXT_OBS_COMPLETE} *LTM 승격 완료*\n"
                    f">`승격 0건 | 기각 {result.rejected_count}건`",
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
            compact_quote = _blockquote(result.compacted)
            archive_info = f"\n>`archive: {archive_path}`" if archive_path else ""
            _send_debug_log(
                debug_channel,
                f":compression: *LTM 장기 기억 압축*\n"
                f">`{_format_tokens(persistent_tokens)} → {_format_tokens(result.token_count)} tok`"
                f"{archive_info}\n"
                f"{compact_quote}",
                thread_ts=anchor_ts,
            )

    except Exception as e:
        logger.error(f"Compactor 파이프라인 오류: {e}")
