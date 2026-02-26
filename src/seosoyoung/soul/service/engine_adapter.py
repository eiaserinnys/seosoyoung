"""soul 엔진 어댑터

slackbot.claude.agent_runner의 ClaudeRunner를 soul API용으로 래핑합니다.
ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환하여
기존 soul 스트리밍 인터페이스와 호환합니다.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Awaitable, Callable, List, Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner
from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType
from seosoyoung.soul.config import get_settings

if TYPE_CHECKING:
    from seosoyoung.soul.service.runner_pool import ClaudeRunnerPool
from seosoyoung.soul.models import (
    CompactEvent,
    CompleteEvent,
    ContextUsageEvent,
    DebugEvent,
    ErrorEvent,
    InterventionSentEvent,
    ProgressEvent,
    ResultSSEEvent,
    SessionEvent,
    TextDeltaSSEEvent,
    TextEndSSEEvent,
    TextStartSSEEvent,
    ToolResultSSEEvent,
    ToolStartSSEEvent,
)

logger = logging.getLogger(__name__)

# soul API용 도구 설정 (기본값: 요청에서 도구 목록이 지정되지 않은 경우 사용)
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "Task",
    "WebFetch", "WebSearch", "Edit", "Write", "Bash",
]
DEFAULT_DISALLOWED_TOOLS = ["NotebookEdit", "TodoWrite"]

# 컨텍스트 관련 상수
DEFAULT_MAX_CONTEXT_TOKENS = 200_000

# sentinel: 스트리밍 종료 신호
_DONE = object()


class _CardTracker:
    """SSE 이벤트용 카드 ID 관리 + text↔tool 관계 추적

    AssistantMessage의 TextBlock 하나를 '카드'로 추상화합니다.
    카드 ID는 UUID4 기반 8자리 식별자로 생성됩니다.

    SDK는 TextBlock을 청크 스트리밍하지 않으므로 TEXT_DELTA 하나가
    하나의 완전한 카드에 해당합니다.
    """

    def __init__(self) -> None:
        self._current_card_id: Optional[str] = None
        self._last_tool_name: Optional[str] = None

    def new_card(self) -> str:
        """새 카드 ID 생성 및 현재 카드로 설정

        Returns:
            생성된 카드 ID (8자리 hex)
        """
        self._current_card_id = uuid.uuid4().hex[:8]
        return self._current_card_id

    @property
    def current_card_id(self) -> Optional[str]:
        """현재 활성 카드 ID (thinking 블록 없이 tool이 오면 None)"""
        return self._current_card_id

    def set_last_tool(self, tool_name: str) -> None:
        """마지막 도구 이름 기록 (TOOL_RESULT에서 tool_name 폴백용)"""
        self._last_tool_name = tool_name

    @property
    def last_tool(self) -> Optional[str]:
        """마지막으로 호출된 도구 이름"""
        return self._last_tool_name


@dataclass
class InterventionMessage:
    """개입 메시지 데이터"""
    text: str
    user: str
    attachment_paths: List[str]


def _extract_context_usage(usage: Optional[dict]) -> Optional[ContextUsageEvent]:
    """EngineResult.usage에서 컨텍스트 사용량 이벤트 생성"""
    if not usage:
        return None

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_used = input_tokens + output_tokens

    if total_used <= 0:
        return None

    max_tokens = DEFAULT_MAX_CONTEXT_TOKENS
    percent = (total_used / max_tokens) * 100 if max_tokens > 0 else 0

    logger.info(
        f"Context usage: input={input_tokens:,}, output={output_tokens:,}, "
        f"total={total_used:,}/{max_tokens:,} ({percent:.1f}%)"
    )

    return ContextUsageEvent(
        used_tokens=total_used,
        max_tokens=max_tokens,
        percent=round(percent, 1),
    )


def _build_intervention_prompt(msg: InterventionMessage) -> str:
    """개입 메시지를 Claude 프롬프트로 변환"""
    if msg.attachment_paths:
        attachment_info = "\n".join([f"- {p}" for p in msg.attachment_paths])
        return (
            f"[사용자 개입 메시지 from {msg.user}]\n"
            f"{msg.text}\n\n"
            f"첨부 파일 (Read 도구로 확인):\n"
            f"{attachment_info}"
        )
    return f"[사용자 개입 메시지 from {msg.user}]\n{msg.text}"


class SoulEngineAdapter:
    """ClaudeRunner -> AsyncIterator[SSE Event] 어댑터

    ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
    asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환합니다.
    기존 soul의 ClaudeCodeRunner.execute()와 동일한 인터페이스를 제공합니다.
    """

    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        pool: Optional["ClaudeRunnerPool"] = None,
    ):
        self._workspace_dir = workspace_dir or get_settings().workspace_dir
        self._pool = pool

    def _resolve_mcp_config_path(self) -> Optional[Path]:
        """WORKSPACE_DIR 기준으로 mcp_config.json 경로를 해석"""
        config_path = Path(self._workspace_dir) / "mcp_config.json"
        if config_path.exists():
            return config_path
        return None

    async def execute(
        self,
        prompt: str,
        resume_session_id: Optional[str] = None,
        get_intervention: Optional[Callable[[], Awaitable[Optional[dict]]]] = None,
        on_intervention_sent: Optional[Callable[[str, str], Awaitable[None]]] = None,
        *,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        use_mcp: bool = True,
    ) -> AsyncIterator:
        """Claude Code 실행 (SSE 이벤트 스트림)

        기존 soul의 ClaudeCodeRunner.execute()와 동일한 인터페이스.

        Args:
            prompt: 사용자 프롬프트
            resume_session_id: 이전 세션 ID
            get_intervention: 개입 메시지 가져오기 함수
            on_intervention_sent: 개입 전송 후 콜백
            allowed_tools: 허용 도구 목록 (None이면 기본값 사용)
            disallowed_tools: 금지 도구 목록 (None이면 기본값 사용)
            use_mcp: MCP 서버 연결 여부

        Yields:
            ProgressEvent | InterventionSentEvent | ContextUsageEvent
            | CompactEvent | DebugEvent | CompleteEvent | ErrorEvent
        """
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # 요청별 도구 설정 적용 (None이면 기본값 사용)
        effective_allowed = allowed_tools if allowed_tools is not None else DEFAULT_ALLOWED_TOOLS
        effective_disallowed = disallowed_tools if disallowed_tools is not None else DEFAULT_DISALLOWED_TOOLS

        # MCP 설정
        mcp_config_path = self._resolve_mcp_config_path() if use_mcp else None

        # debug_send_fn: 동기 콜백 → 큐 어댑터
        # ClaudeRunner._debug()는 동기 함수이므로 call_soon_threadsafe로 큐에 enqueue
        def debug_send_fn(message: str) -> None:
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    DebugEvent(message=message),
                )
            except Exception:
                pass  # 큐 닫힘 등 무시

        # --- 콜백 → 큐 어댑터 ---

        async def on_progress(text: str) -> None:
            await queue.put(ProgressEvent(text=text))

        async def on_compact(trigger: str, message: str) -> None:
            await queue.put(CompactEvent(trigger=trigger, message=message))

        async def on_intervention_callback() -> Optional[str]:
            """인터벤션 폴링: dict → prompt 문자열 변환"""
            if not get_intervention:
                return None

            intervention = await get_intervention()
            if not intervention:
                return None

            msg = InterventionMessage(
                text=intervention.get("text", ""),
                user=intervention.get("user", ""),
                attachment_paths=intervention.get("attachment_paths", []),
            )

            # 이벤트 발행 + 콜백 호출
            await queue.put(InterventionSentEvent(user=msg.user, text=msg.text))
            if on_intervention_sent:
                await on_intervention_sent(msg.user, msg.text)

            return _build_intervention_prompt(msg)

        # --- 세션 ID 조기 통지 ---

        async def on_session_callback(session_id: str) -> None:
            """ClaudeRunner가 SystemMessage에서 session_id를 받으면 즉시 SSE 이벤트 발행"""
            await queue.put(SessionEvent(session_id=session_id))

        # --- 세분화 이벤트 (dashboard용) ---

        tracker = _CardTracker()

        async def on_engine_event(event: EngineEvent) -> None:
            """ClaudeRunner 엔진 이벤트 → 세분화 SSE 이벤트 변환

            기존 on_progress/on_compact 이벤트와 병행 발행됩니다.
            슬랙봇 하위호환 유지: 기존 이벤트를 대체하지 않습니다.
            """
            if event.type == EngineEventType.TEXT_DELTA:
                text = event.data.get("text", "")
                # TextBlock 전체 = 하나의 카드 (SDK는 청크 스트리밍 미지원)
                card_id = tracker.new_card()
                await queue.put(TextStartSSEEvent(card_id=card_id))
                await queue.put(TextDeltaSSEEvent(card_id=card_id, text=text))
                await queue.put(TextEndSSEEvent(card_id=card_id))

            elif event.type == EngineEventType.TOOL_START:
                tool_name = event.data.get("tool_name", "")
                tool_input = event.data.get("tool_input", {})
                # SSE 페이로드 크기 제한: 대형 tool_input 방지
                try:
                    import json as _json
                    tool_input_str = _json.dumps(tool_input, ensure_ascii=False)
                    if len(tool_input_str) > 2000:
                        tool_input = {"_truncated": tool_input_str[:2000] + "..."}
                except (TypeError, ValueError):
                    tool_input = {"_error": "serialize_failed"}
                tracker.set_last_tool(tool_name)
                await queue.put(ToolStartSSEEvent(
                    card_id=tracker.current_card_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                ))

            elif event.type == EngineEventType.TOOL_RESULT:
                result = event.data.get("result", "")
                is_error = event.data.get("is_error", False)
                # tool_name은 이벤트 페이로드 우선, 없으면 tracker 폴백
                tool_name = event.data.get("tool_name") or tracker.last_tool or ""
                await queue.put(ToolResultSSEEvent(
                    card_id=tracker.current_card_id,
                    tool_name=tool_name,
                    result=result,
                    is_error=is_error,
                ))

            elif event.type == EngineEventType.RESULT:
                success = event.data.get("success", False)
                output = event.data.get("output", "")
                error = event.data.get("error")
                await queue.put(ResultSSEEvent(
                    success=success,
                    output=output,
                    error=error,
                ))

        # --- 백그라운드 실행 ---

        async def run_claude() -> None:
            # 풀이 있으면 acquire, 없으면 직접 생성
            if self._pool is not None:
                runner = await self._pool.acquire(session_id=resume_session_id)
                # W-3: 풀에서 꺼낸 runner에 요청별 debug_send_fn 주입
                runner.debug_send_fn = debug_send_fn
                # W-4: 풀에서 꺼낸 runner에 요청별 도구 설정 주입
                runner.allowed_tools = effective_allowed
                runner.disallowed_tools = effective_disallowed
            else:
                runner = ClaudeRunner(
                    thread_ts="",
                    working_dir=Path(self._workspace_dir),
                    allowed_tools=effective_allowed,
                    disallowed_tools=effective_disallowed,
                    mcp_config_path=mcp_config_path,
                    debug_send_fn=debug_send_fn,
                )

            success = False
            try:
                result = await runner.run(
                    prompt=prompt,
                    session_id=resume_session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    on_intervention=on_intervention_callback,
                    on_session=on_session_callback,
                    on_event=on_engine_event,
                )

                # 컨텍스트 사용량 이벤트
                ctx_event = _extract_context_usage(result.usage)
                if ctx_event:
                    await queue.put(ctx_event)

                # 완료/에러 이벤트
                if result.success and not result.is_error:
                    final_text = result.output or "(결과 없음)"
                    await queue.put(CompleteEvent(
                        result=final_text,
                        attachments=[],
                        claude_session_id=result.session_id,
                    ))
                    success = True
                    # 성공 시 풀에 반환
                    if self._pool is not None:
                        await self._pool.release(runner, session_id=result.session_id)
                else:
                    error_msg = result.error or result.output or "실행 오류"
                    await queue.put(ErrorEvent(message=error_msg))
                    # C-1: 에러 시 runner 폐기 (오염 방지)
                    if self._pool is not None:
                        await self._pool._discard(runner, reason="run_error")

            except Exception as e:
                logger.exception(f"SoulEngineAdapter execution error: {e}")
                await queue.put(ErrorEvent(message=f"실행 오류: {str(e)}"))
                # C-1: 예외 시 runner 폐기 (고아 프로세스 방지)
                if self._pool is not None:
                    await self._pool._discard(runner, reason="exception")

            finally:
                await queue.put(_DONE)

        # 백그라운드 태스크 시작
        task = asyncio.create_task(run_claude())

        try:
            while True:
                event = await queue.get()
                if event is _DONE:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


# 싱글톤 인스턴스 (lifespan에서 init_soul_engine()으로 재초기화 가능)
soul_engine = SoulEngineAdapter()


def init_soul_engine(pool: Optional["ClaudeRunnerPool"] = None) -> SoulEngineAdapter:
    """soul_engine 싱글톤을 (재)초기화한다.

    lifespan에서 풀 생성 후 호출하여 싱글톤을 교체한다.

    Args:
        pool: 주입할 ClaudeRunnerPool. None이면 풀 없이 초기화.

    Returns:
        새로 생성된 SoulEngineAdapter 인스턴스
    """
    global soul_engine
    soul_engine = SoulEngineAdapter(pool=pool)
    return soul_engine
