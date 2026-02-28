"""rescue-bot 엔진 어댑터

rescue.claude.agent_runner의 ClaudeRunner를 rescue-bot용으로 래핑합니다.
rescue-bot 전용 설정(working_dir, 도구 제한)을 적용하여
ClaudeRunner 인스턴스를 생성하고, interrupt/compact 등의 제어를 위임합니다.

채널/스레드 정보는 메인 봇과 동일하게 프롬프트 내 <slack-context> 블록을 통해
Claude에 전달되며, env 주입은 사용하지 않습니다.
"""

import logging
from typing import Optional

from seosoyoung.rescue.config import RescueConfig
from seosoyoung.rescue.claude.agent_runner import (
    ClaudeRunner,
    get_runner as _get_runner,
)
from seosoyoung.rescue.claude.engine_types import EngineResult
from seosoyoung.utils.async_bridge import run_in_new_loop

logger = logging.getLogger(__name__)

ALLOWED_TOOLS = None  # None = 모든 도구 허용
DISALLOWED_TOOLS = ["WebFetch", "WebSearch", "Task"]


def create_runner(thread_ts: str = "") -> ClaudeRunner:
    """rescue-bot용 ClaudeRunner를 생성합니다.

    Args:
        thread_ts: 스레드 타임스탬프 (세션 키)
    """
    return ClaudeRunner(
        thread_ts=thread_ts,
        working_dir=RescueConfig.get_working_dir(),
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
    )


def interrupt(thread_ts: str) -> bool:
    """실행 중인 스레드에 인터럽트 전송"""
    runner = _get_runner(thread_ts)
    if runner is None:
        return False
    return runner.interrupt()


def compact_session_sync(session_id: str) -> EngineResult:
    """세션 컴팩트 (동기)"""
    runner = create_runner()
    return run_in_new_loop(runner.compact_session(session_id))
