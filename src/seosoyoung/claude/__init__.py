"""Claude Code 연동"""

from pathlib import Path
from typing import Optional

from seosoyoung.claude.agent_runner import (
    ClaudeAgentRunner,
    ClaudeResult,
    ClaudeRunner,
    get_runner,
    register_runner,
    remove_runner,
    shutdown_all,
    shutdown_all_sync,
)


def get_claude_runner(
    working_dir: Optional[Path] = None,
    timeout: int = 300,
    allowed_tools: Optional[list[str]] = None,
    disallowed_tools: Optional[list[str]] = None,
    mcp_config_path: Optional[Path] = None,
) -> ClaudeRunner:
    """Claude 실행기 인스턴스를 반환하는 팩토리 함수

    thread_ts가 없는 일회성 작업(compact 등)에 사용합니다.
    thread_ts가 있는 정규 세션에는 ClaudeRunner(thread_ts=..., ...)를 직접 생성하세요.

    Args:
        working_dir: 작업 디렉토리 (기본값: 현재 디렉토리)
        timeout: 타임아웃 (초)
        allowed_tools: 허용할 도구 목록
        disallowed_tools: 금지할 도구 목록
        mcp_config_path: MCP 서버 설정 파일 경로

    Returns:
        ClaudeRunner 인스턴스
    """
    return ClaudeRunner(
        working_dir=working_dir,
        timeout=timeout,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        mcp_config_path=mcp_config_path,
    )


__all__ = [
    "get_claude_runner",
    "ClaudeRunner",
    "ClaudeAgentRunner",
    "ClaudeResult",
    "get_runner",
    "register_runner",
    "remove_runner",
    "shutdown_all",
    "shutdown_all_sync",
]
