"""세션 컨텍스트 주입

세션 생성 시 채널 대화 맥락을 구성합니다.
모니터링 채널이면 judged/pending 데이터를 병합하여 더 풍부한 컨텍스트를 제공합니다.
"""

import logging
from decimal import Decimal
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ChannelStoreProtocol(Protocol):
    """ChannelStore가 구현해야 하는 인터페이스"""

    def load_judged(self, channel_id: str) -> list[dict]: ...
    def load_pending(self, channel_id: str) -> list[dict]: ...

MAX_INITIAL_MESSAGES = 7


def build_initial_context(
    channel_id: str,
    slack_messages: list[dict],
    monitored_channels: list[str],
    channel_store: Optional[ChannelStoreProtocol],
) -> dict:
    """세션 최초 생성 시 채널 컨텍스트를 구성합니다.

    Args:
        channel_id: 슬랙 채널 ID
        slack_messages: 슬랙 API로 가져온 최근 메시지 목록
        monitored_channels: 모니터링 대상 채널 ID 목록
        channel_store: ChannelStore 인스턴스 (모니터링 채널 아니면 None 가능)

    Returns:
        {
            "messages": list[dict],  # 시간순 정렬된 메시지 (최대 7개)
            "last_seen_ts": str,     # 가장 마지막 메시지의 ts
            "source_type": str,      # "thread" | "hybrid"
        }
    """
    is_monitored = channel_id in monitored_channels and channel_store is not None

    if is_monitored:
        source_type = "hybrid"
        # judged + pending + slack 메시지 병합
        judged = channel_store.load_judged(channel_id)
        pending = channel_store.load_pending(channel_id)
        all_messages = _merge_messages(judged, pending, slack_messages)
    else:
        source_type = "thread"
        all_messages = list(slack_messages)

    # 시간순 정렬 (Decimal로 float 정밀도 손실 방지)
    all_messages.sort(key=lambda m: Decimal(m.get("ts", "0")))

    # 최대 7개로 제한 (가장 최근)
    if len(all_messages) > MAX_INITIAL_MESSAGES:
        all_messages = all_messages[-MAX_INITIAL_MESSAGES:]

    last_seen_ts = all_messages[-1]["ts"] if all_messages else ""

    return {
        "messages": all_messages,
        "last_seen_ts": last_seen_ts,
        "source_type": source_type,
    }


MAX_FOLLOWUP_MESSAGES = 10


def build_followup_context(
    channel_id: str,
    last_seen_ts: str,
    channel_store: Optional[ChannelStoreProtocol],
    monitored_channels: list[str],
) -> dict:
    """후속 요청 시 last_seen_ts 이후 미전송 메시지를 구성합니다.

    모니터링 채널이면 judged/pending에서 last_seen_ts 이후 메시지를 가져오고
    linked 체인 정보도 포함합니다.

    Args:
        channel_id: 슬랙 채널 ID
        last_seen_ts: 마지막으로 세션에 전달된 메시지의 ts
        channel_store: ChannelStore 인스턴스
        monitored_channels: 모니터링 대상 채널 ID 목록

    Returns:
        {
            "messages": list[dict],  # 시간순 정렬된 미전송 메시지
            "last_seen_ts": str,     # 업데이트된 last_seen_ts
        }
    """
    is_monitored = channel_id in monitored_channels and channel_store is not None

    if not is_monitored or not last_seen_ts:
        return {"messages": [], "last_seen_ts": last_seen_ts}

    # judged + pending에서 last_seen_ts 이후 메시지 수집
    judged = channel_store.load_judged(channel_id)
    pending = channel_store.load_pending(channel_id)
    all_messages = _merge_messages(judged, pending)

    # last_seen_ts 이후 메시지만 필터링 (Decimal로 float 정밀도 손실 방지)
    cutoff = Decimal(last_seen_ts)
    unseen = [m for m in all_messages if Decimal(m.get("ts", "0")) > cutoff]

    # linked 체인 정보: unseen 메시지가 참조하는 이전 메시지도 포함
    linked_ts_set = set()
    for msg in unseen:
        linked_ts = msg.get("linked_message_ts")
        if linked_ts and Decimal(linked_ts) <= cutoff:
            linked_ts_set.add(linked_ts)

    # linked 메시지 수집 (already seen이지만 참조 대상으로 포함)
    linked_messages = []
    if linked_ts_set:
        for msg in all_messages:
            if msg.get("ts") in linked_ts_set:
                linked_messages.append(msg)

    # 병합 후 시간순 정렬
    combined = _merge_messages(linked_messages, unseen)
    combined.sort(key=lambda m: Decimal(m.get("ts", "0")))

    # 최대 제한
    if len(combined) > MAX_FOLLOWUP_MESSAGES:
        combined = combined[-MAX_FOLLOWUP_MESSAGES:]

    new_last_seen = combined[-1]["ts"] if combined else last_seen_ts

    return {
        "messages": combined,
        "last_seen_ts": new_last_seen,
    }


def format_hybrid_context(messages: list[dict], source_type: str) -> str:
    """hybrid 세션용 채널 컨텍스트를 프롬프트 텍스트로 포맷합니다.

    Args:
        messages: 시간순 정렬된 메시지 목록
        source_type: "thread" | "channel" | "hybrid"

    Returns:
        포맷된 컨텍스트 문자열
    """
    if not messages:
        return ""

    if source_type == "hybrid":
        header = (
            "[이 세션은 채널 대화와 스레드가 연결된 hybrid 세션입니다]\n"
            "[아래는 채널에서 수집된 최근 대화입니다]"
        )
    else:
        header = "아래는 Slack 채널의 최근 대화입니다:"

    lines = []
    for msg in messages:
        user = msg.get("user", "unknown")
        text = msg.get("text", "")
        linked = msg.get("linked_message_ts", "")
        line = f"<{user}>: {text}"
        if linked:
            line += f" [linked:{linked}]"
        lines.append(line)

    return f"{header}\n\n" + "\n".join(lines)


def _merge_messages(*sources: list[dict]) -> list[dict]:
    """여러 메시지 소스를 ts 기준으로 중복 제거하며 병합합니다.

    먼저 나오는 소스의 메시지가 우선합니다 (judged > pending > slack).
    """
    seen_ts = set()
    merged = []
    for source in sources:
        for msg in source:
            ts = msg.get("ts", "")
            if ts and ts not in seen_ts:
                seen_ts.add(ts)
                merged.append(msg)
    return merged
