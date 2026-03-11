"""진행 상태 콜백 팩토리

executor._execute_once()에서 추출한 이벤트 콜백 생성 로직입니다.
PresentationContext를 캡처하는 클로저 집합을 반환합니다.
"""

import asyncio
import logging
import os
from seosoyoung.slackbot.formatting import (
    format_initial_placeholder,
    format_thinking_initial,
    format_thinking_text,
    format_thinking_complete,
    format_tool_initial,
    format_tool_result,
    build_input_request_blocks,
)
from seosoyoung.slackbot.presentation.activity_board import ActivityBoard
from seosoyoung.slackbot.presentation.node_map import SlackNodeMap
from seosoyoung.slackbot.presentation.redact import redact_sensitive
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.slack.formatting import update_message

logger = logging.getLogger(__name__)


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
    return float(os.environ["SOULSTREAM_EVENT_DELETE_DELAY"])


def _thinking_delete_delay() -> float:
    """thinking 메시지 삭제 전 대기 시간 (초) — 호출 시점에 환경변수를 읽음"""
    return float(os.environ["SOULSTREAM_THINKING_DELETE_DELAY"])


def build_event_callbacks(
    pctx: PresentationContext,
    node_map: SlackNodeMap,
    mode: str = "clean",
    initial_placeholder_ts: str | None = None,
    initial_board: "ActivityBoard | None" = None,
) -> dict:
    """세분화 이벤트 콜백 + on_compact 팩토리

    Args:
        pctx: 프레젠테이션 컨텍스트
        node_map: 이벤트-메시지 매핑
        mode: "clean" = 일반 채널(갱신 모드, 완료 후 삭제),
              "keep" = DM 채널(풀 덤프 모드, 완료 후 유지)
        initial_placeholder_ts: 초기 placeholder 메시지의 ts (cleanup()에서 삭제)
        initial_board: ActivityBoard 인스턴스 (clean 모드에서 B placeholder 관리용)

    Returns:
        {
            "on_thinking": ...,
            "on_text_start": ...,
            "on_text_delta": ...,
            "on_text_end": ...,
            "on_tool_start": ...,
            "on_tool_result": ...,
            "on_compact": ...,
            "cleanup": ...,
        }
    """

    # placeholder 삭제 상태 관리
    _placeholder_ts: list[str | None] = [initial_placeholder_ts]
    # text 누적 버퍼 (clean 모드에서 placeholder에 텍스트를 누적)
    _text_buffer: list[str] = [""]
    # ActivityBoard (clean 모드에서만 사용)
    _board: list[ActivityBoard | None] = [initial_board]
    # compact 항목 ID 추적
    _compact_item_id: list[str | None] = [None]
    _compact_counter: list[int] = [0]

    def _next_compact_id() -> str:
        _compact_counter[0] += 1
        return f"compact_{_compact_counter[0]}"

    async def cleanup():
        """실행 완료 후 placeholder A·B 삭제"""
        # A 삭제
        ts = _placeholder_ts[0]
        if ts:
            _placeholder_ts[0] = None
            try:
                pctx.client.chat_delete(channel=pctx.channel, ts=ts)
            except Exception as e:
                logger.debug(f"placeholder A 삭제 실패: {e}")
        # B 삭제 (pending tasks 취소 후)
        board = _board[0]
        if board:
            board.cancel_all_pending()
            try:
                pctx.client.chat_delete(channel=pctx.channel, ts=board.msg_ts)
            except Exception as e:
                logger.debug(f"placeholder B 삭제 실패: {e}")

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

    async def _schedule_thinking_delete(msg_ts: str) -> None:
        """clean 모드 전용: thinking 메시지를 설정된 시간 후 삭제

        create_task로 호출되므로 예외가 호출자에게 전파되지 않는다.
        delay 읽기를 포함한 전체를 try/except로 감싸서 조용히 처리한다.
        """
        try:
            delay = _thinking_delete_delay()
            if delay > 0:
                await asyncio.sleep(delay)
            pctx.client.chat_delete(channel=pctx.channel, ts=msg_ts)
            logger.debug(f"thinking 메시지 삭제 성공: ts={msg_ts}")
        except Exception as e:
            logger.debug(f"thinking 메시지 삭제 실패 (무시): ts={msg_ts}, err={e}")

    async def on_thinking(thinking_text: str, event_id, parent_event_id):
        try:
            if mode == "clean" and _board[0] is not None:
                item_id = f"thinking_{event_id}"
                content = format_thinking_text(thinking_text)
                delay = _thinking_delete_delay()  # add 전에 읽어서 실패 시 항목이 남지 않게
                _board[0].add(item_id, content)
                _board[0].schedule_remove(item_id, delay)
            else:
                # keep 모드 또는 board 생성 실패 시: 기존 로직 그대로
                text = format_thinking_text(thinking_text)
                reply = pctx.client.chat_postMessage(
                    channel=pctx.channel,
                    thread_ts=pctx.thread_ts,
                    text=text,
                )
                msg_ts = reply["ts"]
                node = node_map.add_thinking(event_id, msg_ts, parent_event_id)
                if thinking_text:
                    node.text_buffer = thinking_text
                # [clean 모드만] 설정된 시간 후 자동 삭제
                if mode == "clean":
                    asyncio.create_task(_schedule_thinking_delete(msg_ts))
        except Exception as e:
            logger.warning(f"thinking 메시지 생성 실패: {e}")

    async def on_text_start(event_id, parent_event_id):
        try:
            if mode == "clean":
                # clean 모드: placeholder를 재사용하여 텍스트 누적 시작
                _text_buffer[0] = ""
            else:
                # full dump 모드: 새 슬랙 메시지를 생성하여 text 노드로 등록
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
            if mode == "clean":
                # clean 모드: placeholder에 누적 텍스트 갱신
                _text_buffer[0] += text
                ts = _placeholder_ts[0]
                if ts:
                    display_text = format_thinking_text(_text_buffer[0])
                    update_message(pctx.client, pctx.channel, ts, display_text)
            else:
                # full dump 모드: text 노드 찾아서 갱신
                node = node_map.find_text_node(parent_event_id)
                if not node:
                    logger.debug(f"text_delta: text 노드 없음 (parent_event_id={parent_event_id})")
                    return
                node.text_buffer += text
                display_text = format_thinking_text(node.text_buffer)
                update_message(pctx.client, pctx.channel, node.msg_ts, display_text)
        except Exception as e:
            logger.warning(f"text_delta 갱신 실패: {e}")

    async def on_text_end(event_id, parent_event_id):
        try:
            if mode == "clean":
                # clean 모드: placeholder의 텍스트를 완료 상태로 갱신
                ts = _placeholder_ts[0]
                if ts:
                    display_text = format_thinking_complete(_text_buffer[0])
                    try:
                        update_message(pctx.client, pctx.channel, ts, display_text)
                    except Exception as e:
                        logger.warning(f"text_end 갱신 실패: {e}")
            else:
                # full dump 모드: text 노드를 완료 처리
                node = node_map.find_text_node(parent_event_id)
                if not node:
                    logger.debug(f"text_end: text 노드 없음 (event_id={event_id}, parent_event_id={parent_event_id})")
                    return
                # SSE 재연결 시 이미 처리한 이벤트가 재생될 수 있음 — 중복 방지
                if node.completed:
                    logger.debug(f"text_end: 이미 완료된 노드 (event_id={node.event_id}), skip")
                    return
                logger.debug(f"text_end: 노드 발견 (node.event_id={node.event_id}, node.msg_ts={node.msg_ts}, mode={mode})")
                node_map.mark_completed_and_remove(node.event_id)

                display_text = format_thinking_complete(node.text_buffer or "")
                try:
                    update_message(pctx.client, pctx.channel, node.msg_ts, display_text)
                except Exception as e:
                    logger.warning(f"text_end 갱신 실패: {e}")
        except Exception as e:
            logger.warning(f"text_end 처리 실패: {e}")

    async def on_tool_start(tool_name: str, tool_input, tool_use_id: str, event_id, parent_event_id):
        try:
            if mode == "clean" and _board[0] is not None:
                item_id = f"tool_{event_id}"
                content = format_tool_initial(tool_name, tool_input)
                _board[0].add(item_id, content)
                node_map.add_tool(event_id, "", tool_use_id, parent_event_id, tool_name)
            else:
                # keep 모드 또는 board 생성 실패 시: 기존 로직 그대로
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

            # 민감 정보 REDACT 처리 (슬랙에 노출되기 전)
            safe_result = redact_sensitive(result) if isinstance(result, str) else result

            # [공통] 결과 내용으로 교체 + 완료 이모지
            display_text = format_tool_result(tool_name, safe_result, is_error=is_error)

            if mode == "clean" and _board[0] is not None:
                item_id = f"tool_{node.event_id}"
                delay = _event_delete_delay()  # update 전에 읽어서 실패 시 항목이 갱신되지 않게
                _board[0].update(item_id, display_text)
                _board[0].schedule_remove(item_id, delay)
            else:
                # keep 모드 또는 board 생성 실패 시: 기존 로직 그대로
                try:
                    update_message(pctx.client, pctx.channel, node.msg_ts, display_text)
                except Exception as e:
                    logger.warning(f"tool_result 갱신 실패: {e}")
                # [clean 모드만] 설정된 시간 후 삭제
                if mode == "clean":
                    await _schedule_delete(node.msg_ts)
        except Exception as e:
            logger.warning(f"tool_result 처리 실패: {e}")

    async def on_input_request(request_id: str, questions: list, agent_session_id: str):
        """AskUserQuestion 이벤트 수신 → Block Kit 버튼 메시지 게시"""
        try:
            blocks = build_input_request_blocks(request_id, questions, agent_session_id)
            if not blocks:
                logger.warning(f"input_request: 빈 질문 목록 (request_id={request_id})")
                return

            reply = pctx.client.chat_postMessage(
                channel=pctx.channel,
                thread_ts=pctx.thread_ts,
                blocks=blocks,
                text="질문에 응답해주세요",  # fallback text
            )
            msg_ts = reply["ts"]

            # 응답 전달에 필요한 메타데이터를 node_map에 저장
            node_map.add_input_request(
                request_id=request_id,
                msg_ts=msg_ts,
                questions=questions,
                agent_session_id=agent_session_id,
            )
        except Exception as e:
            logger.warning(f"input_request 메시지 게시 실패: {e}")

    # on_compact 콜백
    async def on_compact(trigger: str, message: str):
        try:
            if mode == "clean" and _board[0] is not None:
                # 이전 compact 항목이 있으면 제거
                old_id = _compact_item_id[0]
                if old_id:
                    _board[0].remove(old_id)
                # 새 compact 항목 추가 (schedule_remove 없음 — 다음 compact 또는
                # cleanup이 제거. 압축 진행 중임을 사용자에게 계속 보여주기 위함)
                new_id = _next_compact_id()
                text = ("🔄 컨텍스트가 자동 압축됩니다..." if trigger == "auto"
                        else "📦 컨텍스트를 압축하는 중입니다...")
                _board[0].add(new_id, text)
                _compact_item_id[0] = new_id
            else:
                # keep 모드 또는 board 생성 실패 시: 기존 로직 그대로
                if pctx.compact_msg_ts:
                    try:
                        update_message(pctx.client, pctx.channel, pctx.compact_msg_ts, "✅ 컴팩트가 완료됐습니다")
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
        except Exception as e:
            logger.warning(f"컴팩션 알림 전송 실패: {e}")

    return {
        "on_thinking": on_thinking,
        "on_text_start": on_text_start,
        "on_text_delta": on_text_delta,
        "on_text_end": on_text_end,
        "on_tool_start": on_tool_start,
        "on_tool_result": on_tool_result,
        "on_input_request": on_input_request,
        "on_compact": on_compact,
        "cleanup": cleanup,
    }
