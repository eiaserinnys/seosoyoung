"""Claude Code 연동"""

import threading
from pathlib import Path
from typing import Optional

from seosoyoung.claude.agent_runner import ClaudeAgentRunner, ClaudeResult

# 역할별 runner 캐시
_runner_cache: dict[str, ClaudeAgentRunner] = {}
_cache_lock = threading.Lock()


def get_claude_runner(
    working_dir: Optional[Path] = None,
    timeout: int = 300,
    allowed_tools: Optional[list[str]] = None,
    disallowed_tools: Optional[list[str]] = None,
    mcp_config_path: Optional[Path] = None,
    cache_key: Optional[str] = None,
) -> ClaudeAgentRunner:
    """Claude 실행기 인스턴스를 반환하는 팩토리 함수

    Args:
        working_dir: 작업 디렉토리 (기본값: 현재 디렉토리)
        timeout: 타임아웃 (초)
        allowed_tools: 허용할 도구 목록
        disallowed_tools: 금지할 도구 목록
        mcp_config_path: MCP 서버 설정 파일 경로
        cache_key: 캐시 키 (없으면 새 인스턴스, 있으면 캐시된 인스턴스 반환)

    Returns:
        ClaudeAgentRunner 인스턴스
    """
    if cache_key is None:
        # 캐시 키 없으면 새 인스턴스 (기존 동작 유지)
        return ClaudeAgentRunner(
            working_dir=working_dir,
            timeout=timeout,
            allowed_tools=allowed_tools,
            disallowed_tools=disallowed_tools,
            mcp_config_path=mcp_config_path,
        )

    with _cache_lock:
        if cache_key not in _runner_cache:
            _runner_cache[cache_key] = ClaudeAgentRunner(
                working_dir=working_dir,
                timeout=timeout,
                allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                mcp_config_path=mcp_config_path,
            )
        return _runner_cache[cache_key]


def clear_runner_cache() -> int:
    """runner 캐시를 비웁니다 (테스트용)

    Returns:
        제거된 캐시 항목 수
    """
    with _cache_lock:
        count = len(_runner_cache)
        _runner_cache.clear()
        return count


def get_cached_runner_count() -> int:
    """캐시된 runner 수를 반환합니다 (테스트/디버그용)"""
    with _cache_lock:
        return len(_runner_cache)


__all__ = [
    "get_claude_runner",
    "ClaudeAgentRunner",
    "ClaudeResult",
    "clear_runner_cache",
    "get_cached_runner_count",
]
