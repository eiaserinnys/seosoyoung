"""GitPoller - 원격 저장소 변경 감지"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("supervisor")


class GitPoller:
    """git fetch 후 로컬/원격 HEAD를 비교하여 변경 감지."""

    def __init__(
        self,
        repo_path: Path,
        remote: str = "origin",
        branch: str = "main",
    ) -> None:
        self.repo_path = repo_path
        self.remote = remote
        self.branch = branch
        self.local_head: str | None = None
        self.remote_head: str | None = None

    def check(self) -> bool:
        """원격에 새 커밋이 있는지 확인. 네트워크 오류 시 False 반환."""
        try:
            self._fetch()
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("git fetch 실패 (무시): %s", exc)
            return False

        try:
            self.local_head = self._rev_parse("HEAD")
            self.remote_head = self._rev_parse(f"{self.remote}/{self.branch}")
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("git rev-parse 실패: %s", exc)
            return False

        changed = self.local_head != self.remote_head
        if changed:
            logger.info(
                "변경 감지: local=%s remote=%s",
                self.local_head[:8],
                self.remote_head[:8],
            )
        return changed

    def reset(self) -> None:
        """저장된 HEAD 값 초기화."""
        self.local_head = None
        self.remote_head = None

    def _fetch(self) -> None:
        """git fetch 실행."""
        result = subprocess.run(
            ["git", "fetch", self.remote, self.branch],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"git fetch 실패 (rc={result.returncode}): {result.stderr.strip()}"
            )

    def _rev_parse(self, ref: str) -> str:
        """git rev-parse로 커밋 해시 조회."""
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"git rev-parse {ref} 실패: {result.stderr.strip()}"
            )
        return result.stdout.strip()
