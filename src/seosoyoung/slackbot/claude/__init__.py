"""Claude Code 연동 — Soulstream 서버에 위임하여 실행"""

from seosoyoung.slackbot.claude.types import (
    CardInfo,
    SlackClient,
    SayFunction,
    ProgressCallback,
    CompactCallback,
)
from seosoyoung.slackbot.claude.engine_types import ClaudeResult


def get_claude_runner():
    """rescue 모듈의 ClaudeRunner 인스턴스를 생성하여 반환합니다."""
    from seosoyoung.rescue.claude.agent_runner import ClaudeRunner
    return ClaudeRunner()


__all__ = [
    "ClaudeResult",
    "CardInfo",
    "SlackClient",
    "SayFunction",
    "ProgressCallback",
    "CompactCallback",
    "get_claude_runner",
]
