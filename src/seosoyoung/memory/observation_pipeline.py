"""관찰 파이프라인

세션 종료 시 대화를 버퍼에 누적하고, 누적 토큰이 임계치를 넘으면 Observer를 트리거합니다.
Mastra의 원본 구현처럼 상한선(threshold) 기반으로 동작합니다.

흐름:
1. 세션 대화를 세션(thread_ts)별 pending 버퍼에 append
2. pending 토큰 합산 → 임계치 미만이면 저장만 하고 종료
3. 임계치 이상이면 Observer 호출 → 관찰 로그 갱신 → pending 비우기
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축
"""

import logging
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


def _progress_bar(current: int, total: int, width: int = 10) -> str:
    """프로그레스 바 생성. 예: ■■■■□□□□□□"""
    if total <= 0:
        return "□" * width
    filled = min(round(current / total * width), width)
    return "■" * filled + "□" * (width - filled)


def _short_ts(thread_ts: str) -> str:
    """thread_ts를 짧은 식별자로 변환. 예: 1234567890.123456 → ...3456"""
    if len(thread_ts) > 4:
        return f"...{thread_ts[-4:]}"
    return thread_ts


async def observe_conversation(
    store: MemoryStore,
    observer: Observer,
    thread_ts: str,
    user_id: str,
    messages: list[dict],
    observation_threshold: int = 30000,
    reflector: Optional[Reflector] = None,
    reflection_threshold: int = 20000,
    debug_channel: str = "",
) -> bool:
    """대화를 버퍼에 누적하고, 임계치 도달 시 관찰합니다.

    Args:
        store: 관찰 로그 저장소
        observer: Observer 인스턴스
        thread_ts: 세션(스레드) 타임스탬프 — 저장 키
        user_id: 사용자 ID — 메타데이터용
        messages: 이번 세션 대화 내역
        observation_threshold: Observer 트리거 토큰 임계치
        reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
        reflection_threshold: Reflector 트리거 토큰 임계치
        debug_channel: 디버그 로그를 발송할 슬랙 채널

    Returns:
        True: 관찰 수행됨, False: 버퍼에 누적만 함 또는 실패
    """
    sid = _short_ts(thread_ts)
    log_label = f"session={thread_ts}"
    debug_ts = ""

    try:
        token_counter = TokenCounter()

        # 1. 이번 세션 대화를 pending 버퍼에 누적 (thread_ts 기준)
        store.append_pending_messages(thread_ts, messages)

        # 2. 누적된 전체 pending 메시지 로드 및 토큰 계산
        all_pending = store.load_pending_messages(thread_ts)
        pending_tokens = token_counter.count_messages(all_pending)

        # 기존 관찰 로그 로드 (세션별)
        record = store.get_record(thread_ts)
        existing_observations = record.observations if record else None

        # 디버그: 시작 메시지 발송
        if debug_channel:
            debug_ts = _send_debug_log(
                debug_channel,
                f":mag: *OM Observer 시작...* `{sid}`",
            )

        # 3. 임계치 미달이면 저장만 하고 종료
        if pending_tokens < observation_threshold:
            logger.info(
                f"관찰 대기 ({log_label}): "
                f"{pending_tokens}/{observation_threshold} tokens"
            )
            if debug_channel:
                bar = _progress_bar(pending_tokens, observation_threshold)
                _update_debug_log(
                    debug_channel,
                    debug_ts,
                    f":black_right_pointing_double_triangle_with_vertical_bar: *OM 버퍼 누적* "
                    f"`{sid} | {bar} {_format_tokens(pending_tokens)}/{_format_tokens(observation_threshold)}`",
                )
            return False

        # 4. 임계치 도달 → Observer 호출
        result = await observer.observe(
            existing_observations=existing_observations,
            messages=all_pending,
        )

        if result is None:
            logger.warning(f"Observer가 None을 반환 ({log_label})")
            if debug_channel:
                _update_debug_log(
                    debug_channel,
                    debug_ts,
                    f":warning: *OM Observer 결과 없음* `{sid}`",
                )
            return False

        # 5. 관찰 로그 갱신
        new_tokens = token_counter.count_string(result.observations)

        if record is None:
            record = MemoryRecord(thread_ts=thread_ts, user_id=user_id)

        old_observations = record.observations
        record.observations = result.observations
        record.observation_tokens = new_tokens
        record.last_observed_at = datetime.now(timezone.utc)
        record.total_sessions_observed += 1

        # 6. Reflector: 임계치 초과 시 압축
        if reflector and new_tokens > reflection_threshold:
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
                    f"{new_tokens} → {reflection_result.token_count} tokens, "
                    f"총 {record.reflection_count}회 압축"
                )

        # 7. 저장 및 pending 비우기
        store.save_record(record)
        store.clear_pending_messages(thread_ts)

        logger.info(
            f"관찰 완료 ({log_label}): "
            f"{record.observation_tokens} tokens, "
            f"총 {record.total_sessions_observed}회"
        )

        # 디버그: 성공 메시지로 수정
        if debug_channel:
            diff = _make_observation_diff(old_observations, record.observations)
            diff_block = f"\n```\n{diff}\n```" if diff else ""
            _update_debug_log(
                debug_channel,
                debug_ts,
                f":white_check_mark: *OM 관찰 완료* "
                f"`{sid} | {_format_tokens(record.observation_tokens)} tokens | "
                f"관찰 {record.total_sessions_observed}회`"
                f"{diff_block}",
            )
        return True

    except Exception as e:
        logger.error(f"관찰 파이프라인 오류 ({log_label}): {e}")
        if debug_channel:
            _update_debug_log(
                debug_channel,
                debug_ts,
                f":x: *OM 오류* `{sid} | {e}`",
            )
        return False


def _make_observation_diff(old: str, new: str) -> str:
    """관찰 로그의 변경점을 간략히 표시.

    새로 추가된 줄에 + 접두사, 삭제된 줄에 - 접두사를 붙입니다.
    너무 길면 truncate합니다.
    """
    if not old:
        # 첫 관찰이면 전체를 보여줌
        lines = new.strip().split("\n")
        result = "\n".join(f"+ {line}" for line in lines[:20])
        if len(lines) > 20:
            result += f"\n... (+{len(lines) - 20} lines)"
        return result

    old_lines = set(old.strip().split("\n"))
    new_lines = new.strip().split("\n")

    added = []
    for line in new_lines:
        if line not in old_lines and line.strip():
            added.append(f"+ {line}")

    if not added:
        return "(변경 없음)"

    result = "\n".join(added[:20])
    if len(added) > 20:
        result += f"\n... (+{len(added) - 20} lines)"
    return result
