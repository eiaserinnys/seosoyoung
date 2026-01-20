"""Claude Code 연동

서비스 팩토리:
- CLAUDE_USE_SDK=true: SDK 기반 ClaudeAgentRunner 사용
- CLAUDE_USE_SDK=false (기본값): CLI 기반 ClaudeRunner 사용
"""

from pathlib import Path
from typing import Optional, Union

from seosoyoung.config import Config
from seosoyoung.claude.runner import ClaudeRunner, ClaudeResult


def get_claude_runner(
    working_dir: Optional[Path] = None,
    timeout: int = 300,
    allowed_tools: Optional[list[str]] = None,
    disallowed_tools: Optional[list[str]] = None,
    mcp_config_path: Optional[Path] = None,
) -> Union["ClaudeRunner", "ClaudeAgentRunner"]:
    """Claude 실행기 인스턴스를 반환하는 팩토리 함수

    CLAUDE_USE_SDK 환경변수에 따라 SDK 기반 또는 CLI 기반 실행기를 반환합니다.

    Args:
        working_dir: 작업 디렉토리 (기본값: 현재 디렉토리)
        timeout: 타임아웃 (초)
        allowed_tools: 허용할 도구 목록
        disallowed_tools: 금지할 도구 목록
        mcp_config_path: MCP 서버 설정 파일 경로 (SDK 모드에서만 사용)

    Returns:
        ClaudeRunner 또는 ClaudeAgentRunner 인스턴스
    """
    if Config.CLAUDE_USE_SDK:
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner
        return ClaudeAgentRunner(
            working_dir=working_dir,
            timeout=timeout,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            mcp_config_path=mcp_config_path,
        )
    else:
        return ClaudeRunner(
            working_dir=working_dir,
            timeout=timeout,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
        )


__all__ = [
    "get_claude_runner",
    "ClaudeRunner",
    "ClaudeResult",
]
