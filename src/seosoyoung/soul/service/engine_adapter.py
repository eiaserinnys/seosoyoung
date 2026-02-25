"""soul 엔진 어댑터

slackbot.claude.agent_runner의 ClaudeRunner를 soul API용으로 래핑합니다.
ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환하여
기존 soul 스트리밍 인터페이스와 호환합니다.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, List, Optional

from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner
from seosoyoung.soul.config import get_settings
from seosoyoung.soul.models import (
    CompactEvent,
    CompleteEvent,
    ContextUsageEvent,
    ErrorEvent,
    InterventionSentEvent,
    ProgressEvent,
)

logger = logging.getLogger(__name__)

# soul API용 도구 설정
ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "Task",
    "WebFetch", "WebSearch", "Edit", "Write", "Bash",
]
DISALLOWED_TOOLS = ["NotebookEdit", "TodoWrite"]

# 컨텍스트 관련 상수
DEFAULT_MAX_CONTEXT_TOKENS = 200_000

# sentinel: 스트리밍 종료 신호
_DONE = object()


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

    def __init__(self, workspace_dir: Optional[str] = None):
        self._workspace_dir = workspace_dir or get_settings().workspace_dir

    async def execute(
        self,
        prompt: str,
        resume_session_id: Optional[str] = None,
        get_intervention: Optional[Callable[[], Awaitable[Optional[dict]]]] = None,
        on_intervention_sent: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> AsyncIterator:
        """Claude Code 실행 (SSE 이벤트 스트림)

        기존 soul의 ClaudeCodeRunner.execute()와 동일한 인터페이스.

        Args:
            prompt: 사용자 프롬프트
            resume_session_id: 이전 세션 ID
            get_intervention: 개입 메시지 가져오기 함수
            on_intervention_sent: 개입 전송 후 콜백

        Yields:
            ProgressEvent | InterventionSentEvent | ContextUsageEvent
            | CompactEvent | CompleteEvent | ErrorEvent
        """
        queue: asyncio.Queue = asyncio.Queue()

        runner = ClaudeRunner(
            thread_ts="",
            working_dir=Path(self._workspace_dir),
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
        )

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

        # --- 백그라운드 실행 ---

        async def run_claude() -> None:
            try:
                result = await runner.run(
                    prompt=prompt,
                    session_id=resume_session_id,
                    on_progress=on_progress,
                    on_compact=on_compact,
                    on_intervention=on_intervention_callback,
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
                else:
                    error_msg = result.error or result.output or "실행 오류"
                    await queue.put(ErrorEvent(message=error_msg))

            except Exception as e:
                logger.exception(f"SoulEngineAdapter execution error: {e}")
                await queue.put(ErrorEvent(message=f"실행 오류: {str(e)}"))

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


# 싱글톤 인스턴스
soul_engine = SoulEngineAdapter()
