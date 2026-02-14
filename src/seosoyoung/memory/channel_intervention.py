"""채널 개입(intervention) 모듈

ChannelObserverResult를 InterventionAction으로 변환하고
슬랙 API로 발송하며 개입 이력을 관리합니다.

흐름:
1. parse_intervention_markup: 관찰 결과 → 액션 리스트
2. InterventionHistory.filter_actions: 리액션 필터링
3. execute_interventions: 슬랙 API 발송
4. send_debug_log: 디버그 채널에 로그 전송
"""

import json
import logging
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from seosoyoung.config import Config
from seosoyoung.memory.channel_observer import ChannelObserverResult, JudgeItem

logger = logging.getLogger(__name__)


@dataclass
class InterventionAction:
    """개입 액션"""

    type: str  # "message" | "react"
    target: str  # "channel" | thread_ts | message_ts
    content: str  # 메시지 텍스트 or 이모지 이름


def parse_intervention_markup(result: ChannelObserverResult) -> list[InterventionAction]:
    """ChannelObserverResult를 InterventionAction 리스트로 변환합니다.

    Args:
        result: ChannelObserver의 관찰 결과

    Returns:
        실행할 InterventionAction 리스트 (비어있을 수 있음)
    """
    if result.reaction_type == "none":
        return []

    if not result.reaction_target or not result.reaction_content:
        return []

    if result.reaction_type == "react":
        return [
            InterventionAction(
                type="react",
                target=result.reaction_target,
                content=result.reaction_content,
            )
        ]

    if result.reaction_type == "intervene":
        target = result.reaction_target
        # "thread:{ts}" → ts만 추출
        if target.startswith("thread:"):
            target = target[len("thread:"):]

        return [
            InterventionAction(
                type="message",
                target=target,
                content=result.reaction_content,
            )
        ]

    return []


async def execute_interventions(
    client,
    channel_id: str,
    actions: list[InterventionAction],
) -> list[Optional[dict]]:
    """InterventionAction 리스트를 슬랙 API로 발송합니다.

    Args:
        client: Slack WebClient
        channel_id: 대상 채널
        actions: 실행할 액션 리스트

    Returns:
        각 액션의 API 응답 (실패 시 None)
    """
    results = []

    for action in actions:
        try:
            if action.type == "message":
                if action.target == "channel":
                    resp = client.chat_postMessage(
                        channel=channel_id,
                        text=action.content,
                    )
                else:
                    resp = client.chat_postMessage(
                        channel=channel_id,
                        text=action.content,
                        thread_ts=action.target,
                    )
                results.append(resp)

            elif action.type == "react":
                resp = client.reactions_add(
                    channel=channel_id,
                    timestamp=action.target,
                    name=action.content,
                )
                results.append(resp)

            else:
                logger.warning(f"알 수 없는 액션 타입: {action.type}")
                results.append(None)

        except Exception as e:
            logger.error(f"개입 실행 실패 ({action.type}): {e}")
            results.append(None)

    return results


def intervention_probability(
    minutes_since_last: float, recent_count: int
) -> float:
    """시간 감쇠와 빈도 감쇠를 기반으로 개입 확률을 계산합니다.

    Args:
        minutes_since_last: 마지막 개입으로부터 경과 시간(분)
        recent_count: 최근 2시간 내 개입 횟수

    Returns:
        0.0~1.0 사이의 확률 값
    """
    # 시간 감쇠: 0분→0.0, 30분→~0.5, 60분→~0.8, 120분→~1.0
    time_factor = 1 - math.exp(-minutes_since_last / 40)
    # 빈도 감쇠: 최근 2시간 내 개입 횟수가 많을수록 억제
    freq_factor = 1 / (1 + recent_count * 0.3)
    base = time_factor * freq_factor
    # ±20% 랜덤 흔들림
    jitter = random.uniform(0.8, 1.2)
    return min(base * jitter, 1.0)


class InterventionHistory:
    """개입 이력 관리

    상태 머신 없이, 개입 이력(history 배열)만으로 확률 기반 개입을 지원합니다.

    intervention.meta.json 구조:
    {
        "history": [
            {"at": 1770974000, "type": "message"},
            {"at": 1770970000, "type": "message"}
        ]
    }
    """

    HISTORY_WINDOW_MINUTES = 120  # 2시간

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _meta_path(self, channel_id: str) -> Path:
        return self.base_dir / "channel" / channel_id / "intervention.meta.json"

    def _read_meta(self, channel_id: str) -> dict:
        path = self._meta_path(channel_id)
        if not path.exists():
            return {"history": []}
        data = json.loads(path.read_text(encoding="utf-8"))
        # 이전 형식과의 호환: history 키가 없으면 초기화
        if "history" not in data:
            return {"history": []}
        return data

    def _write_meta(self, channel_id: str, meta: dict) -> None:
        path = self._meta_path(channel_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prune_history(self, history: list[dict]) -> list[dict]:
        """2시간 초과 항목을 제거합니다."""
        cutoff = time.time() - self.HISTORY_WINDOW_MINUTES * 60
        return [entry for entry in history if entry.get("at", 0) >= cutoff]

    def record(self, channel_id: str, entry_type: str = "message") -> None:
        """개입 이력을 기록합니다.

        Args:
            channel_id: 채널 ID
            entry_type: 기록 유형 ("message" 등)
        """
        meta = self._read_meta(channel_id)
        meta["history"] = self._prune_history(meta["history"])
        meta["history"].append({"at": time.time(), "type": entry_type})
        self._write_meta(channel_id, meta)

    def minutes_since_last(self, channel_id: str) -> float:
        """마지막 개입으로부터 경과 시간(분)을 반환합니다.

        이력이 없으면 무한대를 반환합니다.
        """
        meta = self._read_meta(channel_id)
        history = meta.get("history", [])
        if not history:
            return float("inf")
        last_at = max(entry.get("at", 0) for entry in history)
        if last_at == 0:
            return float("inf")
        return (time.time() - last_at) / 60.0

    def recent_count(
        self, channel_id: str, window_minutes: int = 120
    ) -> int:
        """최근 window_minutes 내 개입 횟수를 반환합니다."""
        meta = self._read_meta(channel_id)
        cutoff = time.time() - window_minutes * 60
        return sum(
            1 for entry in meta.get("history", [])
            if entry.get("at", 0) >= cutoff
        )

    def can_react(self, channel_id: str) -> bool:
        """이모지 리액션은 항상 허용"""
        return True

    def filter_actions(
        self, channel_id: str, actions: list[InterventionAction]
    ) -> list[InterventionAction]:
        """액션을 필터링합니다.

        - react 타입: 항상 통과
        - message 타입: 항상 통과 (확률 판단은 pipeline에서 처리)

        Returns:
            필터링된 액션 리스트
        """
        return [a for a in actions if a.type in ("react", "message")]


# 하위호환 별칭
CooldownManager = InterventionHistory


def _build_fields_blocks(fields: list[tuple[str, str]]) -> list[dict]:
    """(label, value) 쌍 리스트를 2열 표 형식의 Block Kit 블록 리스트로 변환합니다.

    왼쪽에 항목명(*bold*), 오른쪽에 값이 나오도록 라벨과 값을 별도 field로 배치합니다.
    section.fields는 최대 10개이므로, 5쌍(=10 fields)씩 section 블록을 분할합니다.
    """
    block_fields = []
    for label, value in fields:
        block_fields.append({"type": "mrkdwn", "text": f"*{label}*"})
        block_fields.append({"type": "mrkdwn", "text": value})

    # 10개씩(5행) 분할
    blocks = []
    for i in range(0, len(block_fields), 10):
        chunk = block_fields[i:i + 10]
        blocks.append({"type": "section", "fields": chunk})
    return blocks


async def send_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    observer_result: ChannelObserverResult,
    actions: list[InterventionAction],
    actions_filtered: list[InterventionAction],
    reasoning: Optional[str] = None,
    emotion: Optional[str] = None,
    pending_count: int = 0,
    reaction_detail: Optional[str] = None,
) -> None:
    """디버그 채널에 관찰 결과 로그를 전송합니다 (Block Kit 형식)."""
    if not debug_channel:
        return

    skipped = len(actions) - len(actions_filtered)
    action_summary = ", ".join(
        f"{a.type}→{a.target}" for a in actions_filtered
    ) or "(없음)"

    fields = [
        ("채널", f"`{source_channel}`"),
        ("중요도", f"{observer_result.importance}/10"),
        ("반응", observer_result.reaction_type),
        ("실행 액션", action_summary),
        ("쿨다운 스킵", f"{skipped}건"),
    ]
    if pending_count > 0:
        fields.append(("pending", f"{pending_count}건"))
    if reaction_detail:
        fields.append(("리액션 상세", reaction_detail))
    if emotion:
        fields.append(("감정", emotion))
    if reasoning:
        fields.append(("판단 이유", reasoning))

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Channel Observer"}},
        *_build_fields_blocks(fields),
    ]

    fallback = (
        f"[Channel Observer] {source_channel} | "
        f"중요도: {observer_result.importance}/10 | "
        f"반응: {observer_result.reaction_type}"
    )

    try:
        client.chat_postMessage(channel=debug_channel, blocks=blocks, text=fallback)
    except Exception as e:
        logger.error(f"디버그 로그 전송 실패: {e}")


def send_collect_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    buffer_tokens: int,
    threshold: int,
    message_text: str = "",
    user: str = "",
    is_thread: bool = False,
) -> None:
    """메시지 수집 시 디버그 채널에 로그를 전송합니다 (Block Kit 형식)."""
    if not debug_channel:
        return

    location = "스레드" if is_thread else "채널"
    preview = message_text[:80]
    if len(message_text) > 80:
        preview += "..."
    ratio = f"{buffer_tokens}/{threshold}"

    trigger_text = ""
    if buffer_tokens >= threshold:
        trigger_text = " → 소화 트리거"

    fields = [
        ("채널", f"`{source_channel}`"),
        ("위치", location),
        ("작성자", f"<{user}>"),
        ("메시지", preview or "(없음)"),
        ("버퍼", f"`{ratio} tok`{trigger_text}"),
    ]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": ":memo: 채널 수집"}},
        *_build_fields_blocks(fields),
    ]

    fallback = f"[채널 수집] {source_channel} | {location} | {ratio} tok"

    try:
        client.chat_postMessage(channel=debug_channel, blocks=blocks, text=fallback)
    except Exception as e:
        logger.error(f"수집 디버그 로그 전송 실패: {e}")


def send_digest_skip_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    buffer_tokens: int,
    threshold: int,
) -> None:
    """소화 스킵(임계치 미달) 시 디버그 채널에 로그를 전송합니다 (Block Kit 형식)."""
    if not debug_channel:
        return

    fields = [
        ("채널", f"`{source_channel}`"),
        ("상태", "소화 스킵"),
        ("버퍼", f"{buffer_tokens} tok"),
        ("임계치", f"{threshold} tok"),
    ]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": ":pause_button: 소화 스킵"}},
        *_build_fields_blocks(fields),
    ]

    fallback = f"[소화 스킵] {source_channel} | 버퍼 {buffer_tokens} tok < 임계치 {threshold} tok"

    try:
        client.chat_postMessage(channel=debug_channel, blocks=blocks, text=fallback)
    except Exception as e:
        logger.error(f"소화 스킵 디버그 로그 전송 실패: {e}")


def send_intervention_probability_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    importance: int,
    time_factor: float,
    freq_factor: float,
    probability: float,
    final_score: float,
    threshold: float,
    passed: bool,
) -> None:
    """확률 기반 개입 판단 결과를 디버그 채널에 기록합니다 (Block Kit 형식)."""
    if not debug_channel:
        return

    emoji = ":white_check_mark:" if passed else ":no_entry_sign:"
    result_symbol = "≥" if passed else "<"

    fields = [
        ("채널", f"`{source_channel}`"),
        ("중요도", f"{importance}/10"),
        ("시간감쇠", f"{time_factor:.2f}"),
        ("빈도감쇠", f"{freq_factor:.2f}"),
        ("확률", f"{probability:.3f}"),
        ("최종", f"{final_score:.3f} {result_symbol} {threshold:.2f}"),
    ]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} 개입 확률 판단"}},
        *_build_fields_blocks(fields),
    ]

    fallback = (
        f"[개입 확률 판단] {source_channel} | "
        f"중요도: {importance}/10 | "
        f"최종: {final_score:.3f} {result_symbol} {threshold:.2f}"
    )

    try:
        client.chat_postMessage(channel=debug_channel, blocks=blocks, text=fallback)
    except Exception as e:
        logger.error(f"개입 확률 디버그 로그 전송 실패: {e}")


def send_multi_judge_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    items: list[JudgeItem],
    react_actions: list[InterventionAction],
    message_actions_executed: list[InterventionAction],
    pending_count: int = 0,
) -> None:
    """복수 판단 결과를 메시지별 독립 블록으로 디버그 채널에 전송합니다."""
    if not debug_channel:
        return

    react_count = len(react_actions)
    intervene_count = len(message_actions_executed)
    none_count = sum(1 for item in items if item.reaction_type == "none")

    # 헤더 블록 + 요약
    blocks = [
        {"type": "header", "text": {
            "type": "plain_text",
            "text": f"Channel Observer ({len(items)} messages)",
        }},
    ]

    summary_fields = [
        {"type": "mrkdwn", "text": f"*채널*"},
        {"type": "mrkdwn", "text": f"`{source_channel}`"},
        {"type": "mrkdwn", "text": f"*pending*"},
        {"type": "mrkdwn", "text": f"{pending_count}건"},
        {"type": "mrkdwn", "text": f"*판단 결과*"},
        {"type": "mrkdwn", "text": f"react {react_count} · intervene {intervene_count} · none {none_count}"},
    ]
    blocks.append({"type": "section", "fields": summary_fields})
    blocks.append({"type": "divider"})

    # 메시지별 블록
    for item in items:
        reaction_text = item.reaction_type
        if item.reaction_type == "react" and item.reaction_content:
            reaction_text = f":{item.reaction_content}:"
        elif item.reaction_type == "intervene":
            target = item.reaction_target or "channel"
            reaction_text = f"intervene → {target}"

        item_fields = [
            {"type": "mrkdwn", "text": f"*메시지 ID*"},
            {"type": "mrkdwn", "text": f"`{item.ts}`"},
            {"type": "mrkdwn", "text": f"*중요도*"},
            {"type": "mrkdwn", "text": f"{item.importance}/10"},
            {"type": "mrkdwn", "text": f"*리액션*"},
            {"type": "mrkdwn", "text": reaction_text},
        ]
        if item.emotion:
            item_fields.extend([
                {"type": "mrkdwn", "text": f"*감정*"},
                {"type": "mrkdwn", "text": item.emotion},
            ])
        if item.reasoning:
            item_fields.extend([
                {"type": "mrkdwn", "text": f"*판단 이유*"},
                {"type": "mrkdwn", "text": item.reasoning},
            ])

        # section.fields 최대 10개씩 분할
        for i in range(0, len(item_fields), 10):
            chunk = item_fields[i:i + 10]
            blocks.append({"type": "section", "fields": chunk})

        blocks.append({"type": "divider"})

    # 마지막 divider 제거
    if blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    fallback = (
        f"[Channel Observer] {source_channel} | "
        f"{len(items)} messages | "
        f"react {react_count} · intervene {intervene_count} · none {none_count}"
    )

    try:
        client.chat_postMessage(channel=debug_channel, blocks=blocks, text=fallback)
    except Exception as e:
        logger.error(f"복수 판단 디버그 로그 전송 실패: {e}")
