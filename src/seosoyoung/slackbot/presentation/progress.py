"""진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.
"""

import asyncio
import logging
import os
import time
from typing import Callable, Tuple

from seosoyoung.slackbot.formatting import (
    truncate_progress_text,
    format_as_blockquote,
    format_trello_progress,
    format_dm_progress,
    format_initial_placeholder,
    format_thinking_initial,
    format_thinking_text,
    format_thinking_complete,
    format_tool_initial,
    format_tool_complete,
    format_tool_error,
    format_tool_result,
)
from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
from seosoyoung.slackbot.presentation.types import PresentationContext

logger = logging.getLogger(__name__)

# 콜백 타입 (engine_types와 동일 시그니처)
ProgressCallback = Callable  # async (str) -> None
CompactCallback = Callable   # async (str, str) -> None

# stale 사고 과정 체크 간격 (초)
_STALE_CHECK_INTERVAL = 10.0

def post_initial_placeholder(client, channel: str, thread_ts: str) -> str | None:
    """초기 placeholder 메시지를 게시하고 ts를 반환

    실패 시 None을 반환합니다. 호출자는 이 ts를 build_event_callbacks의
    initial_placeholder_ts 파라미터로 전달합니다.
    """
    try:
        reply = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=format_initial_placeholder(),
        )
        return reply["ts"]
    except Exception as e:
        logger.warning(f"placeholder 게시 실패: {e}")
        return None


def _event_delete_delay() -> float:
    """이벤트 메시지 삭제 전 대기 시간 (초) — 호출 시점에 환경변수를 읽음"""
    return float(os.environ.get("SOULSTREAM_EVENT_DELETE_DELAY", "3"))


def build_progress_callbacks(
    pctx: PresentationContext,
    update_message_fn: Callable,
) -> Tuple[ProgressCallback, CompactCallback]:
    """PresentationContext를 캡처하는 on_progress/on_compact 클로저 쌍을 생성

    Args:
        pctx: 프레젠테이션 컨텍스트 (mutable - 콜백이 ts 필드를 갱신)
        update_message_fn: (client, channel, ts, text, *, blocks=None) -> None

    Returns:
        (on_progress, on_compact) 콜백 튜플
    """

    async def on_progress(current_text: str):
        try:
            display_text = truncate_progress_text(current_text)
            if not display_text:
                return

            # compact_msg_ts가 있으면 해당 메시지를 완료로 갱신
            if pctx.compact_msg_ts:
                try:
                    pctx.client.chat_update(
                        channel=pctx.channel,
                        ts=pctx.compact_msg_ts,
                        text="✅ 컴팩트가 완료됐습니다",
                    )
                except Exception as e:
                    logger.warning(f"컴팩트 완료 메시지 갱신 실패: {e}")
                pctx.compact_msg_ts = None

            if pctx.is_trello_mode:
                if pctx.dm_channel_id and pctx.dm_thread_ts:
                    quote_text = format_dm_progress(display_text)
                    reply = pctx.client.chat_postMessage(
                        channel=pctx.dm_channel_id,
                        thread_ts=pctx.dm_thread_ts,
                        text=quote_text,
                        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": quote_text}}]
                    )
                    pctx.dm_last_reply_ts = reply["ts"]
                else:
                    if pctx.main_msg_ts:
                        update_text = format_trello_progress(
                            display_text, pctx.trello_card, pctx.session_id or "")
                        update_message_fn(pctx.client, pctx.channel, pctx.main_msg_ts, update_text)
                    else:
                        logger.warning("trello mode progress: main_msg_ts is None, skipping update")
            else:
                # stale 사고 과정 체크 (rate-limited)
                now = time.monotonic()
                if now - pctx._last_stale_check >= _STALE_CHECK_INTERVAL and pctx.last_msg_ts:
                    pctx._last_stale_check = now
                    try:
                        result = pctx.client.conversations_replies(
                            channel=pctx.channel,
                            ts=pctx.thread_ts,
                            oldest=pctx.last_msg_ts,
                            inclusive=False,
                            limit=1,
                        )
                        # Slack conversations_replies는 oldest 파라미터와 무관하게
                        # 스레드 루트(parent) 메시지를 항상 반환하므로, 클라이언트 측에서
                        # last_msg_ts보다 실제로 newer한 메시지만 필터링한다
                        all_messages = result.get("messages", [])
                        messages = [
                            m for m in all_messages
                            if float(m.get("ts", "0")) > float(pctx.last_msg_ts)
                        ]
                        if messages:
                            # 스레드에 새 메시지가 있음 → 사고 과정 메시지가 stale
                            quote_text = format_as_blockquote(display_text)
                            reply = pctx.client.chat_postMessage(
                                channel=pctx.channel,
                                thread_ts=pctx.thread_ts,
                                text=quote_text,
                            )
                            pctx.last_msg_ts = reply["ts"]
                            return
                    except Exception as e:
                        logger.warning(f"stale 체크 실패: {e}")

                if not pctx.last_msg_ts:
                    logger.debug("on_progress: last_msg_ts is None, skipping update")
                    return

                quote_text = format_as_blockquote(display_text)
                try:
                    update_message_fn(pctx.client, pctx.channel, pctx.last_msg_ts, quote_text)
                except Exception as e:
                    logger.warning(f"사고 과정 메시지 갱신 실패, 새 메시지로 대체: {e}")
                    try:
                        reply = pctx.client.chat_postMessage(
                            channel=pctx.channel,
                            thread_ts=pctx.thread_ts,
                            text=quote_text,
                        )
                        pctx.last_msg_ts = reply["ts"]
                    except Exception as e2:
                        logger.warning(f"새 메시지 전송도 실패: {e2}")
        except Exception as e:
            logger.warning(f"사고 과정 메시지 전송 실패: {e}")

    async def on_compact(trigger: str, message: str):
        try:
            # 이전 compact 메시지가 있으면 완료로 갱신
            if pctx.compact_msg_ts:
                try:
                    pctx.client.chat_update(
                        channel=pctx.channel,
                        ts=pctx.compact_msg_ts,
                        text="✅ 컴팩트가 완료됐습니다",
                    )
                except Exception as e:
                    logger.warning(f"이전 컴팩트 완료 메시지 갱신 실패: {e}")

            text = ("🔄 컨텍스트가 자동 압축됩니다..." if trigger == "auto"
                    else "📦 컨텍스트를 압축하는 중입니다...")
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=text,
            )
            pctx.compact_msg_ts = reply["ts"]
            # 컴팩트 직후 즉시 stale 체크하도록 리셋
            pctx._last_stale_check = 0.0
        except Exception as e:
            logger.warning(f"컴팩션 알림 전송 실패: {e}")

    return on_progress, on_compact


def build_event_callbacks(
    pctx: PresentationContext,
    node_map: SlackNodeMap,
    mode: str = "clean",
    initial_placeholder_ts: str | None = None,
) -> dict:
    """세분화 이벤트 콜백 + on_compact 팩토리 (build_progress_callbacks 대체)

    Args:
        pctx: 프레젠테이션 컨텍스트
        node_map: 이벤트-메시지 매핑
        mode: "clean" (갱신 후 삭제) 또는 "keep" (갱신 후 유지)
        initial_placeholder_ts: 초기 placeholder 메시지의 ts (있으면 첫 이벤트에서 삭제)

    Returns:
        {
            "on_progress": ...,
            "on_thinking": ...,
            "on_text_start": ...,
            "on_text_delta": ...,
            "on_text_end": ...,
            "on_tool_start": ...,
            "on_tool_result": ...,
            "on_compact": ...,
            "_cleanup_progress": ...,
        }
    """

    # placeholder 삭제 상태 관리
    _placeholder_ts: list[str | None] = [initial_placeholder_ts]

    async def _delete_placeholder():
        """초기 placeholder 메시지를 삭제 (idempotent)"""
        ts = _placeholder_ts[0]
        if ts:
            _placeholder_ts[0] = None
            try:
                pctx.client.chat_delete(channel=pctx.channel, ts=ts)
            except Exception as e:
                logger.debug(f"placeholder 삭제 실패: {e}")

    async def _schedule_delete(msg_ts: str) -> None:
        """clean 모드 전용: 설정된 시간 후 메시지 삭제

        삭제 실패 시 폴백 없음 — 이 함수 호출 전에 메시지는 이미
        format_thinking_complete / format_tool_result로 최종 상태로
        갱신된 상태이므로, 삭제 실패 시 완료된 메시지가 남을 뿐이다.
        """
        delay = _event_delete_delay()
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            pctx.client.chat_delete(channel=pctx.channel, ts=msg_ts)
            logger.debug(f"이벤트 메시지 삭제 성공: ts={msg_ts}")
        except Exception as e:
            logger.debug(f"이벤트 메시지 삭제 실패 (무시): ts={msg_ts}, err={e}")

    async def on_thinking(thinking_text: str, event_id, parent_event_id):
        try:
            await _delete_placeholder()
            # thinking 메시지가 progress를 대체하므로 progress 메시지 정리
            await _cleanup_progress()

            text = format_thinking_text(thinking_text) if thinking_text else format_thinking_initial()
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=text,
            )
            msg_ts = reply["ts"]
            node = node_map.add_thinking(event_id, msg_ts, parent_event_id)
            if thinking_text:
                node.text_buffer = thinking_text
        except Exception as e:
            logger.warning(f"thinking 메시지 생성 실패: {e}")

    async def on_text_start(event_id, parent_event_id):
        try:
            await _delete_placeholder()
            node = node_map.find_thinking_for_text(parent_event_id)
            if node:
                # thinking 노드가 있으면 text_buffer 초기화
                node.text_buffer = ""
            else:
                # 독립 text 노드: 새 스레드 메시지 생성 (S6)
                text = format_thinking_initial()
                reply = pctx.client.chat_postMessage(
                    channel=pctx.channel,
                    thread_ts=pctx.thread_ts,
                    text=text,
                )
                msg_ts = reply["ts"]
                node_map.add_text(event_id, msg_ts, parent_event_id)
        except Exception as e:
            logger.warning(f"text_start 처리 실패: {e}")

    async def on_text_delta(text: str, event_id, parent_event_id):
        try:
            await _delete_placeholder()
            node = node_map.find_thinking_for_text(parent_event_id)
            if not node:
                logger.debug(f"text_delta: thinking 노드 없음 (parent_event_id={parent_event_id})")
                return
            node.text_buffer += text
            display_text = format_thinking_text(node.text_buffer)
            pctx.client.chat_update(
                channel=pctx.channel,
                ts=node.msg_ts,
                text=display_text,
            )
        except Exception as e:
            logger.warning(f"text_delta 갱신 실패: {e}")

    async def on_text_end(event_id, parent_event_id):
        try:
            node = node_map.find_thinking_for_text(parent_event_id)
            if not node:
                logger.debug(f"text_end: thinking 노드 없음 (event_id={event_id}, parent_event_id={parent_event_id})")
                return
            # SSE 재연결 시 이미 처리한 이벤트가 재생될 수 있음 — 중복 방지
            if node.completed:
                logger.debug(f"text_end: 이미 완료된 노드 (event_id={node.event_id}), skip")
                return
            logger.debug(f"text_end: 노드 발견 (node.event_id={node.event_id}, node.msg_ts={node.msg_ts}, mode={mode})")
            node_map.mark_completed_and_remove(node.event_id)

            # [공통] 이모지를 done으로 변경 + 내용 갱신
            display_text = format_thinking_complete(node.text_buffer or "")
            try:
                pctx.client.chat_update(
                    channel=pctx.channel,
                    ts=node.msg_ts,
                    text=display_text,
                )
            except Exception as e:
                logger.warning(f"text_end 갱신 실패: {e}")

            # [clean 모드만] 설정된 시간 후 삭제
            if mode == "clean":
                await _schedule_delete(node.msg_ts)
        except Exception as e:
            logger.warning(f"text_end 처리 실패: {e}")

    async def on_tool_start(tool_name: str, tool_input, tool_use_id: str, event_id, parent_event_id):
        try:
            await _delete_placeholder()
            # tool 메시지가 progress를 대체하므로 progress 메시지 정리
            await _cleanup_progress()

            text = format_tool_initial(tool_name, tool_input)
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=text,
            )
            msg_ts = reply["ts"]
            node_map.add_tool(event_id, msg_ts, tool_use_id, parent_event_id, tool_name)
        except Exception as e:
            logger.warning(f"tool_start 메시지 생성 실패: {e}")

    async def on_tool_result(result, tool_use_id: str, is_error, event_id, parent_event_id):
        try:
            node = node_map.find_tool_by_use_id(tool_use_id)
            if not node:
                return
            # SSE 재연결 시 이미 처리한 이벤트가 재생될 수 있음 — 중복 방지
            if node.completed:
                logger.debug(f"tool_result: 이미 완료된 노드 (event_id={node.event_id}), skip")
                return
            node_map.mark_completed_and_remove(node.event_id)
            tool_name = node.tool_name or "tool"

            # [공통] 결과 내용으로 교체 + 완료 이모지
            display_text = format_tool_result(tool_name, result, is_error=is_error)
            try:
                pctx.client.chat_update(
                    channel=pctx.channel,
                    ts=node.msg_ts,
                    text=display_text,
                )
            except Exception as e:
                logger.warning(f"tool_result 갱신 실패: {e}")

            # [clean 모드만] 설정된 시간 후 삭제
            if mode == "clean":
                await _schedule_delete(node.msg_ts)
        except Exception as e:
            logger.warning(f"tool_result 처리 실패: {e}")

    # on_progress 콜백: 진행 상황 메시지 표시 (이전 progress는 즉시 교체)
    _progress_msg_ts: list[str | None] = [None]  # mutable container for nonlocal

    async def on_progress(current_text: str):
        try:
            await _delete_placeholder()
            display_text = truncate_progress_text(current_text)
            if not display_text:
                return
            quote_text = format_as_blockquote(display_text)

            prev_ts = _progress_msg_ts[0]
            if prev_ts:
                # 이전 progress 메시지를 새 내용으로 갱신 (삭제 대신 update로 깜빡임 방지)
                try:
                    pctx.client.chat_update(
                        channel=pctx.channel,
                        ts=prev_ts,
                        text=quote_text,
                    )
                    return
                except Exception as e:
                    logger.debug(f"progress 메시지 갱신 실패, 새 메시지로 대체: {e}")
                    _progress_msg_ts[0] = None

            # 새 progress 메시지 게시
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=quote_text,
            )
            _progress_msg_ts[0] = reply["ts"]
        except Exception as e:
            logger.warning(f"progress 메시지 전송 실패: {e}")

    async def _cleanup_progress():
        """턴 종료 시 남은 progress 메시지 삭제

        Thread safety: _progress_msg_ts는 두 컨텍스트에서 접근됩니다.
        1. 스트림 내 콜백 (on_progress, on_thinking, on_tool_start) — 단일 async 루프
        2. 실행 완료 후 정리 (run_in_new_loop) — 스트림 종료 후 호출 (겹치지 않음)
        """
        prev_ts = _progress_msg_ts[0]
        if prev_ts:
            _progress_msg_ts[0] = None
            try:
                pctx.client.chat_delete(
                    channel=pctx.channel,
                    ts=prev_ts,
                )
            except Exception as del_err:
                logger.debug(f"progress 메시지 삭제 실패: {del_err}")
                try:
                    pctx.client.chat_update(
                        channel=pctx.channel,
                        ts=prev_ts,
                        text="(done)",
                    )
                except Exception as upd_err:
                    logger.debug(f"progress 폴백 갱신 실패: {upd_err}")

    # on_compact 콜백 (build_progress_callbacks와 동일 텍스트)
    async def on_compact(trigger: str, message: str):
        try:
            # 이전 compact 메시지가 있으면 완료로 갱신
            if pctx.compact_msg_ts:
                try:
                    pctx.client.chat_update(
                        channel=pctx.channel,
                        ts=pctx.compact_msg_ts,
                        text="✅ 컴팩트가 완료됐습니다",
                    )
                except Exception as e:
                    logger.warning(f"이전 컴팩트 완료 메시지 갱신 실패: {e}")

            text = ("🔄 컨텍스트가 자동 압축됩니다..." if trigger == "auto"
                    else "📦 컨텍스트를 압축하는 중입니다...")
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=text,
            )
            pctx.compact_msg_ts = reply["ts"]
            # 컴팩트 직후 즉시 stale 체크하도록 리셋
            pctx._last_stale_check = 0.0
        except Exception as e:
            logger.warning(f"컴팩션 알림 전송 실패: {e}")

    return {
        "on_progress": on_progress,
        "on_thinking": on_thinking,
        "on_text_start": on_text_start,
        "on_text_delta": on_text_delta,
        "on_text_end": on_text_end,
        "on_tool_start": on_tool_start,
        "on_tool_result": on_tool_result,
        "_cleanup_progress": _cleanup_progress,
        "on_compact": on_compact,
    }
