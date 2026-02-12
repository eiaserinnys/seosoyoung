"""SessionMonitor - Claude Code 활성 세션 감지"""

from __future__ import annotations

import logging

import psutil

logger = logging.getLogger("supervisor")

# Claude 관련 프로세스 이름 패턴
_CLAUDE_PROCESS_NAMES = {"claude.exe", "claude"}
# cmdline에 이 문자열이 포함되면 Claude Code 세션으로 판정
_CLAUDE_CMDLINE_MARKERS = {"claude-code", "claude", "@anthropic"}


class SessionMonitor:
    """Windows 프로세스 목록에서 Claude Code 활성 세션을 탐지."""

    def active_session_count(self) -> int:
        """현재 활성 Claude Code 세션 수."""
        try:
            return len(self._find_claude_processes())
        except OSError:
            logger.warning("프로세스 목록 조회 실패")
            return 0

    def is_safe_to_deploy(self) -> bool:
        """배포 안전 여부. 활성 세션이 0이면 True."""
        return self.active_session_count() == 0

    def _find_claude_processes(self) -> list[dict]:
        """Claude Code 관련 프로세스 목록 반환."""
        found = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = proc.info
                name = info.get("name") or ""
                cmdline = info.get("cmdline") or []
                name_lower = name.lower()

                # Claude 데스크톱/CLI 프로세스
                if name_lower in _CLAUDE_PROCESS_NAMES:
                    found.append(info)
                    continue

                # node로 실행된 Claude Code SDK 세션
                cmdline_str = " ".join(cmdline).lower()
                if any(marker in cmdline_str for marker in _CLAUDE_CMDLINE_MARKERS):
                    # 봇 자체 프로세스는 제외
                    if "seosoyoung" not in cmdline_str and "supervisor" not in cmdline_str:
                        found.append(info)

            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        return found
