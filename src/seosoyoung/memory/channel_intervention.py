"""채널 개입(intervention) 모듈

Phase 3: ChannelObserverResult를 InterventionAction으로 변환하고
슬랙 API로 발송하며 쿨다운을 관리합니다.

흐름:
1. parse_intervention_markup: 관찰 결과 → 액션 리스트
2. CooldownManager.filter_actions: 쿨다운 필터링
3. execute_interventions: 슬랙 API 발송
4. send_debug_log: 디버그 채널에 로그 전송
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from seosoyoung.config import Config
from seosoyoung.memory.channel_observer import ChannelObserverResult

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


class CooldownManager:
    """개입 쿨다운 및 개입 모드 상태 관리

    상태 머신: idle ↔ active
    - idle: 일반 상태. 소화 시 intervene 결정 → active 전환
    - active: 개입 모드. 메시지마다 반응하고 턴 소모. 턴 0 → idle + 쿨다운

    intervention.meta.json 구조:
    {
        "last_intervention_at": float,
        "mode": "idle" | "active",
        "remaining_turns": int,
    }
    """

    def __init__(self, base_dir: str | Path, cooldown_sec: int = 1800):
        self.base_dir = Path(base_dir)
        self.cooldown_sec = cooldown_sec

    def _meta_path(self, channel_id: str) -> Path:
        return self.base_dir / "channel" / channel_id / "intervention.meta.json"

    def _read_meta(self, channel_id: str) -> dict:
        path = self._meta_path(channel_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_meta(self, channel_id: str, meta: dict) -> None:
        path = self._meta_path(channel_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def can_intervene(self, channel_id: str) -> bool:
        """대화 개입이 가능한지 확인 (쿨다운 체크)"""
        meta = self._read_meta(channel_id)
        last_at = meta.get("last_intervention_at")
        if last_at is None:
            return True
        return (time.time() - last_at) >= self.cooldown_sec

    def can_react(self, channel_id: str) -> bool:
        """이모지 리액션은 항상 허용"""
        return True

    def record_intervention(self, channel_id: str) -> None:
        """개입 시각을 기록"""
        meta = self._read_meta(channel_id)
        meta["last_intervention_at"] = time.time()
        self._write_meta(channel_id, meta)

    # ── 개입 모드 상태 머신 ──────────────────────────────

    def is_active(self, channel_id: str) -> bool:
        """개입 모드 중인지 확인"""
        meta = self._read_meta(channel_id)
        return meta.get("mode") == "active"

    def get_remaining_turns(self, channel_id: str) -> int:
        """남은 개입 턴 수 반환"""
        meta = self._read_meta(channel_id)
        if meta.get("mode") != "active":
            return 0
        return meta.get("remaining_turns", 0)

    def enter_intervention_mode(self, channel_id: str, max_turns: int) -> None:
        """개입 모드 진입 (idle → active)"""
        meta = self._read_meta(channel_id)
        meta["mode"] = "active"
        meta["remaining_turns"] = max_turns
        self._write_meta(channel_id, meta)

    def consume_turn(self, channel_id: str) -> int:
        """턴 1 소모, 남은 턴 반환. 0이면 idle 전환 + 쿨다운 기록"""
        meta = self._read_meta(channel_id)
        if meta.get("mode") != "active":
            return 0

        remaining = meta.get("remaining_turns", 0) - 1
        if remaining <= 0:
            remaining = 0
            meta["mode"] = "idle"
            meta["remaining_turns"] = 0
            meta["last_intervention_at"] = time.time()
        else:
            meta["remaining_turns"] = remaining

        self._write_meta(channel_id, meta)
        return remaining

    # ── 필터링 ───────────────────────────────────────────

    def filter_actions(
        self, channel_id: str, actions: list[InterventionAction]
    ) -> list[InterventionAction]:
        """쿨다운에 따라 액션을 필터링합니다.

        - active 모드: message 타입도 통과
        - idle 모드: message 타입은 쿨다운 체크
        - react 타입: 항상 통과

        Returns:
            쿨다운을 통과한 액션 리스트
        """
        is_active = self.is_active(channel_id)
        result = []
        for action in actions:
            if action.type == "react":
                result.append(action)
            elif action.type == "message":
                if is_active or self.can_intervene(channel_id):
                    result.append(action)
                else:
                    logger.info(
                        f"쿨다운으로 개입 스킵 ({channel_id}): {action.content[:30]}..."
                    )
        return result


async def send_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    observer_result: ChannelObserverResult,
    actions: list[InterventionAction],
    actions_filtered: list[InterventionAction],
) -> None:
    """디버그 채널에 관찰 결과 로그를 전송합니다.

    Args:
        client: Slack WebClient
        debug_channel: 디버그 로그 채널 ID
        source_channel: 관찰한 원본 채널 ID
        observer_result: 관찰 결과
        actions: 파싱된 전체 액션 리스트
        actions_filtered: 쿨다운 필터 후 실제 실행된 액션 리스트
    """
    if not debug_channel:
        return

    skipped = len(actions) - len(actions_filtered)
    action_summary = ", ".join(
        f"{a.type}→{a.target}" for a in actions_filtered
    ) or "(없음)"

    text = (
        f"*[Channel Observer]* `{source_channel}`\n"
        f"• 중요도: {observer_result.importance}/10\n"
        f"• 반응: {observer_result.reaction_type}\n"
        f"• 실행 액션: {action_summary}\n"
        f"• 쿨다운 스킵: {skipped}건"
    )

    try:
        client.chat_postMessage(channel=debug_channel, text=text)
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
    """메시지 수집 시 디버그 채널에 로그를 전송합니다.

    Args:
        client: Slack WebClient
        debug_channel: 디버그 로그 채널 ID
        source_channel: 관찰 대상 채널 ID
        buffer_tokens: 현재 버퍼 토큰 수
        threshold: 소화 트리거 임계치
        message_text: 수집된 메시지 텍스트
        user: 메시지 작성자
        is_thread: 스레드 메시지 여부
    """
    if not debug_channel:
        return

    location = "스레드" if is_thread else "채널"
    preview = message_text[:80]
    if len(message_text) > 80:
        preview += "..."
    ratio = f"{buffer_tokens}/{threshold}"

    text = (
        f":memo: *[채널 수집]* `{source_channel}`\n"
        f">*{location}* | <{user}> {preview}\n"
        f">`버퍼: {ratio} tok`"
    )

    if buffer_tokens >= threshold:
        text += " → :arrow_forward: 소화 트리거"

    try:
        client.chat_postMessage(channel=debug_channel, text=text)
    except Exception as e:
        logger.error(f"수집 디버그 로그 전송 실패: {e}")


def send_digest_skip_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    buffer_tokens: int,
    threshold: int,
) -> None:
    """소화 스킵(임계치 미달) 시 디버그 채널에 로그를 전송합니다."""
    if not debug_channel:
        return

    text = (
        f":pause_button: *[소화 스킵]* `{source_channel}`\n"
        f">`버퍼 {buffer_tokens} tok < 임계치 {threshold} tok`"
    )

    try:
        client.chat_postMessage(channel=debug_channel, text=text)
    except Exception as e:
        logger.error(f"소화 스킵 디버그 로그 전송 실패: {e}")


def send_intervention_mode_debug_log(
    client,
    debug_channel: str,
    source_channel: str,
    event: str,
    remaining_turns: int = 0,
    max_turns: int = 0,
    response_text: str = "",
    new_messages: list[dict] | None = None,
    error: str = "",
) -> None:
    """개입 모드 이벤트를 디버그 채널에 기록합니다.

    Args:
        client: Slack WebClient
        debug_channel: 디버그 로그 채널 ID
        source_channel: 관찰 대상 채널 ID
        event: 이벤트 종류 ("enter", "respond", "exit", "error")
        remaining_turns: 남은 턴 수
        max_turns: 최대 턴 수 (enter 시)
        response_text: 서소영의 응답 텍스트 (respond 시)
        new_messages: 트리거한 새 메시지 목록 (respond 시)
        error: 에러 메시지 (error 시)
    """
    if not debug_channel:
        return

    if event == "enter":
        text = (
            f":loudspeaker: *[개입 모드 진입]* `{source_channel}`\n"
            f">`최대 {max_turns}턴 동안 채널 대화에 참여합니다`"
        )
    elif event == "respond":
        msg_summary = ""
        if new_messages:
            for msg in new_messages[:3]:
                user = msg.get("user", "?")
                t = msg.get("text", "")[:80]
                msg_summary += f"\n>  <{user}>: {t}"
            if len(new_messages) > 3:
                msg_summary += f"\n>  ... 외 {len(new_messages) - 3}건"

        resp_preview = response_text[:200]
        if len(response_text) > 200:
            resp_preview += "..."

        text = (
            f":speech_balloon: *[개입 모드 반응]* `{source_channel}` "
            f"(남은 턴: {remaining_turns})\n"
            f">*트리거 메시지:*{msg_summary}\n"
            f">*서소영 응답:*\n>{resp_preview}"
        )
    elif event == "exit":
        text = (
            f":zzz: *[개입 모드 종료]* `{source_channel}`\n"
            f">`턴 소진 → 쿨다운 진입`"
        )
    elif event == "error":
        text = (
            f"{Config.EMOJI_TEXT_INTERVENTION_ERROR} *[개입 모드 오류]* `{source_channel}`\n"
            f">`{error}`"
        )
    else:
        return

    try:
        client.chat_postMessage(channel=debug_channel, text=text)
    except Exception as e:
        logger.error(f"개입 모드 디버그 로그 전송 실패: {e}")
