"""진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.
"""

import logging
import time
from typing import Callable, Tuple

from seosoyoung.slackbot.formatting import (
    truncate_progress_text,
    format_as_blockquote,
    format_trello_progress,
    format_dm_progress,
)
from seosoyoung.slackbot.presentation.types import PresentationContext

logger = logging.getLogger(__name__)

# 콜백 타입 (engine_types와 동일 시그니처)
ProgressCallback = Callable  # async (str) -> None
CompactCallback = Callable   # async (str, str) -> None

# stale 사고 과정 체크 간격 (초)
_STALE_CHECK_INTERVAL = 10.0


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
                    update_text = format_trello_progress(
                        display_text, pctx.trello_card, pctx.session_id or "")
                    update_message_fn(pctx.client, pctx.channel, pctx.main_msg_ts, update_text)
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
                        messages = result.get("messages", [])
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
