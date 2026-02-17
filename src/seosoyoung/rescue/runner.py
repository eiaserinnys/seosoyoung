"""Claude Code SDK 경량 실행기

메인 봇의 agent_runner.py에서 OM, 인터벤션, 스트리밍 콜백 등을
제거한 최소 구현입니다.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk._errors import ProcessError
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
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
    error: Optional[str] = None


async def run_claude(prompt: str) -> RescueResult:
    """Claude Code SDK를 호출하고 결과를 반환합니다.

    Stateless: 세션 재개, OM, 인터벤션 등 없이 단발 호출만 수행합니다.
    """
    working_dir = RescueConfig.get_working_dir()
    timeout = RescueConfig.CLAUDE_TIMEOUT

    options = ClaudeCodeOptions(
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        cwd=working_dir,
    )

    logger.info(f"Claude Code SDK 실행 (cwd={working_dir})")

    current_text = ""
    result_text = ""

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                if hasattr(message, "content"):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            current_text = block.text

            elif isinstance(message, ResultMessage):
                if hasattr(message, "result"):
                    result_text = message.result

        output = result_text or current_text

        return RescueResult(success=True, output=output)

    except asyncio.TimeoutError:
        logger.error(f"Claude Code SDK 타임아웃 ({timeout}s)")
        return RescueResult(
            success=False,
            output=current_text,
            error=f"타임아웃: {timeout}초 초과",
        )
    except ProcessError as e:
        logger.error(f"Claude Code CLI 프로세스 오류: exit_code={e.exit_code}")
        return RescueResult(
            success=False,
            output=current_text,
            error=f"Claude Code 프로세스 오류 (exit code: {e.exit_code})",
        )
    except Exception as e:
        logger.exception(f"Claude Code SDK 실행 오류: {e}")
        return RescueResult(
            success=False,
            output=current_text,
            error=str(e),
        )
