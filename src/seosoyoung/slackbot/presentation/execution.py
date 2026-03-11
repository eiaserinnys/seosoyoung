"""실행 오케스트레이션 헬퍼

placeholder 게시 → 콜백 빌드 → executor 실행 → cleanup 패턴과
on_compact 래핑 보일러플레이트를 캡슐화합니다.
"""

import logging
from typing import Callable, TYPE_CHECKING

from seosoyoung.slackbot.presentation.activity_board import ActivityBoard, BOARD_EMPTY_TEXT
from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
from seosoyoung.slackbot.presentation.progress import (
    build_event_callbacks,
    post_initial_placeholder,
)
from seosoyoung.slackbot.presentation.types import PresentationContext

if TYPE_CHECKING:
    from seosoyoung.core.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


def run_with_event_callbacks(
    pctx: PresentationContext,
    executor_fn: Callable,
    executor_kwargs: dict,
    *,
    mode: str = "clean",
    on_compact_override: Callable | None = None,
    on_compact_wrapper: Callable[[Callable], Callable] | None = None,
) -> None:
    """placeholder 게시 → 콜백 빌드 → executor 실행 → cleanup 패턴을 캡슐화

    Args:
        pctx: 프레젠테이션 컨텍스트
        executor_fn: run_claude_in_session 또는 SoulstreamBackendImpl._executor
        executor_kwargs: executor에 전달할 키워드 인자 (prompt, thread_ts 등).
            on_compact와 세분화 이벤트 콜백(on_thinking 등)은 이 헬퍼가 주입합니다.
        mode: "clean" (일반 채널, 완료 후 삭제) 또는 "keep" (DM, 유지)
        on_compact_override: 외부에서 제공된 on_compact — None이면 event_cbs 기본값 사용
        on_compact_wrapper: on_compact를 래핑하는 함수 (예: 메모리 플래그 래핑).
            override와 함께 사용 시, override된 콜백에 wrapper가 적용됩니다.

    """
    placeholder_ts = post_initial_placeholder(
        pctx.client, pctx.channel, pctx.thread_ts,
    )

    # clean 모드: B placeholder 생성
    board = None
    if mode == "clean":
        try:
            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                text=BOARD_EMPTY_TEXT,
            )
            board = ActivityBoard(pctx.client, pctx.channel, reply["ts"])
        except Exception as e:
            logger.warning(f"placeholder B 게시 실패: {e}")

    node_map = SlackNodeMap()
    event_cbs = build_event_callbacks(
        pctx, node_map, mode,
        initial_placeholder_ts=placeholder_ts,
        initial_board=board,
    )

    on_compact = (
        on_compact_override
        if on_compact_override is not None
        else event_cbs["on_compact"]
    )
    if on_compact_wrapper is not None:
        on_compact = on_compact_wrapper(on_compact)

    # on_progress가 executor_kwargs에 포함되어 있으면 제거 (더 이상 사용하지 않음)
    executor_kwargs.pop("on_progress", None)

    executor_fn(
        **executor_kwargs,
        on_compact=on_compact,
        on_thinking=event_cbs["on_thinking"],
        on_text_start=event_cbs["on_text_start"],
        on_text_delta=event_cbs["on_text_delta"],
        on_text_end=event_cbs["on_text_end"],
        on_tool_start=event_cbs["on_tool_start"],
        on_tool_result=event_cbs["on_tool_result"],
        on_input_request=event_cbs["on_input_request"],
    )

    try:
        from seosoyoung.utils.async_bridge import run_in_new_loop
        run_in_new_loop(event_cbs["cleanup"]())
    except Exception as e:
        logger.warning(f"placeholder 삭제 실패 (무시): {e}")


def wrap_on_compact_with_memory(
    on_compact: Callable,
    pm: "PluginManager | None",
    thread_ts: str,
) -> Callable:
    """on_compact 콜백에 MemoryPlugin compact 플래그를 래핑

    MemoryPlugin이 없으면 원본 콜백을 그대로 반환합니다.

    Args:
        on_compact: 원본 on_compact 콜백
        pm: PluginManager 인스턴스 (None 허용)
        thread_ts: 스레드 타임스탬프

    Returns:
        래핑된 on_compact 콜백 (memory 플러그인이 없으면 원본 그대로)
    """
    if not pm or not pm.plugins:
        return on_compact

    memory_plugin = pm.plugins.get("memory")
    if not memory_plugin:
        return on_compact

    original = on_compact

    async def wrapped(trigger, message):
        try:
            memory_plugin.on_compact_flag(thread_ts)
        except Exception as e:
            logger.warning(f"OM inject 플래그 설정 실패 (PreCompact, 무시): {e}")
        await original(trigger, message)

    return wrapped
