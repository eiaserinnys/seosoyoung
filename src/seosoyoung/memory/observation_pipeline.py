"""관찰 파이프라인

매턴마다 Observer를 호출하여 세션 관찰 로그를 갱신하고, 장기 기억 후보를 수집합니다.

흐름:
1. 이번 턴 대화의 토큰을 계산 → 최소 토큰(min_turn_tokens) 미만이면 스킵
2. Observer 호출 (매턴) → 세션 관찰 로그 갱신
3. <candidates> 태그가 있으면 장기 기억 후보 버퍼에 적재
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from seosoyoung.memory.observer import Observer
from seosoyoung.memory.reflector import Reflector
from seosoyoung.memory.store import MemoryRecord, MemoryStore
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


def _send_debug_log(channel: str, text: str) -> str:
    """OM 디버그 로그를 슬랙 채널에 발송. 메시지 ts를 반환."""
    try:
        from seosoyoung.config import Config
        from slack_sdk import WebClient

        client = WebClient(token=Config.SLACK_BOT_TOKEN)
        resp = client.chat_postMessage(channel=channel, text=text)
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


def _short_ts(thread_ts: str) -> str:
    """thread_ts를 짧은 식별자로 변환. 예: 1234567890.123456 → ...3456"""
    if len(thread_ts) > 4:
        return f"...{thread_ts[-4:]}"
    return thread_ts


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
    debug_channel: str = "",
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
        debug_channel: 디버그 로그를 발송할 슬랙 채널

    Returns:
        True: 관찰 수행됨, False: 스킵 또는 실패
    """
    sid = _short_ts(thread_ts)
    log_label = f"session={thread_ts}"
    debug_ts = ""

    try:
        token_counter = TokenCounter()

        # 1. 이번 턴 대화 토큰 계산 → 최소 토큰 미달 시 스킵
        turn_tokens = token_counter.count_messages(messages)

        if turn_tokens < min_turn_tokens:
            logger.info(
                f"관찰 스킵 ({log_label}): "
                f"{turn_tokens} tok < {min_turn_tokens} 최소"
            )
            if debug_channel:
                _send_debug_log(
                    debug_channel,
                    f":next_track_button: *OM* "
                    f"`{sid} | 스킵 ({_format_tokens(turn_tokens)} tok < {_format_tokens(min_turn_tokens)})`",
                )
            return False

        # 2. 기존 관찰 로그 로드
        record = store.get_record(thread_ts)
        existing_observations = record.observations if record else None

        # 디버그 이벤트 #1: 관찰 시작 (send)
        if debug_channel:
            debug_ts = _send_debug_log(
                debug_channel,
                f":mag: *OM* `{sid} | 관찰 시작`",
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
                    f":x: *OM* `{sid} | 관찰 오류 | Observer returned None`",
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
                    _send_debug_log(
                        debug_channel,
                        f":recycle: *OM Reflector* "
                        f"`{sid} | {_format_tokens(pre_tokens)} → {_format_tokens(reflection_result.token_count)} tok`",
                    )

        # 7. 저장 + inject 플래그
        store.save_record(record)
        store.set_inject_flag(thread_ts)

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
            _update_debug_log(
                debug_channel,
                debug_ts,
                f":white_check_mark: *OM* "
                f"`{sid} | 관찰 완료 | {_format_tokens(turn_tokens)} tok{candidate_part}`",
            )
        return True

    except Exception as e:
        logger.error(f"관찰 파이프라인 오류 ({log_label}): {e}")
        if debug_channel:
            error_msg = str(e)[:80]
            _update_debug_log(
                debug_channel,
                debug_ts,
                f":x: *OM* `{sid} | 관찰 오류 | {error_msg}`",
            )
        return False
