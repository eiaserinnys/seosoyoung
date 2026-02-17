"""Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 agent_runner.py에서 OM, 인터벤션, 스트리밍 콜백 등을
제거한 최소 구현입니다. ClaudeSDKClient 기반으로 세션 재개를 지원합니다.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient
from claude_code_sdk._errors import ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
)

from seosoyoung.rescue.config import RescueConfig

logger = logging.getLogger(__name__)

# 최소한의 도구만 허용
ALLOWED_TOOLS = [
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "TodoWrite",
]

DISALLOWED_TOOLS = [
    "WebFetch",
    "WebSearch",
    "Task",
]


@dataclass
class RescueResult:
    """실행 결과"""

    success: bool
    output: str
    session_id: Optional[str] = None
    error: Optional[str] = None


def run_claude_sync(
    prompt: str,
    session_id: Optional[str] = None,
) -> RescueResult:
    """동기 컨텍스트에서 Claude Code SDK를 호출합니다.

    Slack 이벤트 핸들러(동기)에서 직접 호출할 수 있습니다.
    내부적으로 asyncio.run()을 사용하여 매 호출마다 새 이벤트 루프를 생성합니다.
    """
    return asyncio.run(_run_claude(prompt, session_id=session_id))


async def _run_claude(
    prompt: str,
    session_id: Optional[str] = None,
) -> RescueResult:
    """Claude Code SDK를 호출하고 결과를 반환합니다.

    ClaudeSDKClient 기반으로 세션 재개를 지원합니다:
    - session_id가 None이면 새 세션을 시작합니다.
    - session_id가 있으면 해당 세션을 이어서 실행합니다.

    Args:
        prompt: 실행할 프롬프트
        session_id: 이어갈 세션 ID (선택)

    Returns:
        RescueResult (session_id 포함)
    """
    working_dir = RescueConfig.get_working_dir()

    options = ClaudeCodeOptions(
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        cwd=working_dir,
    )

    if session_id:
        options.resume = session_id

    logger.info(f"Claude Code SDK 실행 (cwd={working_dir}, resume={session_id})")

    result_session_id = None
    current_text = ""
    result_text = ""
    idle_timeout = RescueConfig.CLAUDE_TIMEOUT

    client: Optional[ClaudeSDKClient] = None
    try:
        client = ClaudeSDKClient(options=options)
        await client.connect()
        await client.query(prompt)

        aiter = client.receive_response().__aiter__()
        while True:
            try:
                message = await asyncio.wait_for(aiter.__anext__(), timeout=idle_timeout)
            except StopAsyncIteration:
                break

            if isinstance(message, SystemMessage):
                if hasattr(message, "session_id"):
                    result_session_id = message.session_id
                    logger.info(f"세션 ID: {result_session_id}")

            elif isinstance(message, AssistantMessage):
                if hasattr(message, "content"):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            current_text = block.text

            elif isinstance(message, ResultMessage):
                if hasattr(message, "result"):
                    result_text = message.result
                if hasattr(message, "session_id") and message.session_id:
                    result_session_id = message.session_id

        output = result_text or current_text

        return RescueResult(
            success=True,
            output=output,
            session_id=result_session_id,
        )

    except asyncio.TimeoutError:
        logger.error(f"Claude Code SDK 타임아웃 ({idle_timeout}s)")
        return RescueResult(
            success=False,
            output=current_text,
            session_id=result_session_id,
            error=f"타임아웃: {idle_timeout}초 초과",
        )
    except ProcessError as e:
        logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}")
        return RescueResult(
            success=False,
            output=current_text,
            session_id=result_session_id,
            error=f"Claude Code 프로세스 오류 (exit code: {e.exit_code})",
        )
    except Exception as e:
        logger.exception(f"Claude Code SDK 실행 오류: {e}")
        return RescueResult(
            success=False,
            output=current_text,
            session_id=result_session_id,
            error=str(e),
        )
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception as e:
                logger.warning(f"ClaudeSDKClient disconnect 오류 (무시): {e}")
