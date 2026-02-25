"""진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 on_progress/on_compact 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 쌍을 반환합니다.
"""

import logging
from typing import Callable, Tuple

from seosoyoung.slackbot.claude.message_formatter import (
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
                quote_text = format_as_blockquote(display_text)
                update_message_fn(pctx.client, pctx.channel, pctx.last_msg_ts, quote_text)
        except Exception as e:
            logger.warning(f"사고 과정 메시지 전송 실패: {e}")

    async def on_compact(trigger: str, message: str):
        try:
            text = ("🔄 컨텍스트가 자동 압축됩니다..." if trigger == "auto"
                    else "📦 컨텍스트를 압축하는 중입니다...")
            pctx.say(text=text, thread_ts=pctx.thread_ts)
        except Exception as e:
            logger.warning(f"컴팩션 알림 전송 실패: {e}")

    return on_progress, on_compact
