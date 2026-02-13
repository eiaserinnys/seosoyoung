"""SessionMonitor - 봇이 생성한 Claude Code 세션만 감지"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from .process_manager import ProcessManager

logger = logging.getLogger("supervisor")

# 봇이 생성한 자식 프로세스 중 Claude Code CLI로 판정할 이름
_CLAUDE_PROCESS_NAMES = {"claude.exe", "claude"}


class SessionMonitor:
    """봇 프로세스의 자식 중 Claude Code 세션을 탐지.

    시스템 전체를 스캔하지 않고, ProcessManager가 관리하는 봇 프로세스의
    하위 프로세스 트리만 확인하여 사용자의 Claude Desktop/CLI와 구분합니다.
    """

    def __init__(
        self,
        process_manager: ProcessManager,
        bot_name: str = "bot",
    ) -> None:
        self._pm = process_manager
        self._bot_name = bot_name

    def active_session_count(self) -> int:
        """현재 활성 Claude Code 세션 수."""
        try:
            return len(self._find_bot_child_sessions())
        except OSError:
            logger.warning("프로세스 목록 조회 실패")
            return 0

    def is_safe_to_deploy(self) -> bool:
        """배포 안전 여부. 활성 세션이 0이면 True."""
        return self.active_session_count() == 0

    def _find_bot_child_sessions(self) -> list[dict]:
        """봇 프로세스의 자식 중 Claude Code 세션 목록 반환."""
        bot_pid = self._get_bot_pid()
        if bot_pid is None:
            return []

        try:
            bot_proc = psutil.Process(bot_pid)
        except psutil.NoSuchProcess:
            return []

        found = []
        try:
            children = bot_proc.children(recursive=True)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return []

        for child in children:
            try:
                name = (child.name() or "").lower()
                if name in _CLAUDE_PROCESS_NAMES:
                    found.append({"pid": child.pid, "name": name})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        if found:
            pids = [p["pid"] for p in found]
            logger.debug("봇 자식 Claude 세션 감지: %s", pids)

        return found

    def _get_bot_pid(self) -> int | None:
        """ProcessManager에서 봇 프로세스 PID를 가져온다."""
        return self._pm.get_pid(self._bot_name)
