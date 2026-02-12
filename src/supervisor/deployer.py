"""Deployer - 배포 상태 머신"""

from __future__ import annotations

import enum
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .process_manager import ProcessManager
    from .session_monitor import SessionMonitor

logger = logging.getLogger("supervisor")


class DeployState(enum.Enum):
    """배포 상태"""
    IDLE = "idle"
    PENDING = "pending"
    WAITING_SESSIONS = "waiting_sessions"
    DEPLOYING = "deploying"


class Deployer:
    """git 변경 감지 → 세션 대기 → 배포 실행 상태 머신."""

    def __init__(
        self,
        process_manager: ProcessManager,
        session_monitor: SessionMonitor,
        paths: dict[str, Path],
    ) -> None:
        self._pm = process_manager
        self._session_monitor = session_monitor
        self._paths = paths
        self._state = DeployState.IDLE

    @property
    def state(self) -> DeployState:
        return self._state

    def notify_change(self) -> None:
        """git 변경 감지 알림. idle이면 pending으로 전환."""
        if self._state == DeployState.IDLE:
            self._state = DeployState.PENDING
            logger.info("배포 상태: idle → pending")

    def tick(self) -> None:
        """상태 머신 한 스텝 진행."""
        if self._state == DeployState.IDLE:
            return

        if self._state in (DeployState.PENDING, DeployState.WAITING_SESSIONS):
            if self._session_monitor.is_safe_to_deploy():
                self._state = DeployState.DEPLOYING
                logger.info("배포 상태: → deploying (세션 0)")
                try:
                    self._execute_deploy()
                finally:
                    self._state = DeployState.IDLE
            elif self._state == DeployState.PENDING:
                self._state = DeployState.WAITING_SESSIONS
                logger.info("배포 상태: pending → waiting_sessions (세션 대기)")

    def _execute_deploy(self) -> None:
        """배포 실행: stop → update → restart."""
        try:
            logger.info("배포 시작: 프로세스 중지")
            self._pm.stop_all()

            logger.info("배포: 업데이트 수행")
            self._do_update()

            logger.info("배포: 프로세스 재시작")
            for name in self._pm.registered_names:
                self._pm.start(name)

            logger.info("배포 완료")
        except Exception:
            logger.exception("배포 실패, 프로세스 재시작 시도")
            for name in self._pm.registered_names:
                try:
                    self._pm.start(name)
                except Exception:
                    logger.exception("프로세스 재시작 실패: %s", name)

    def _do_update(self) -> None:
        """git pull + pip install (기존 __main__._do_update 로직 이관)."""
        runtime = self._paths["runtime"]
        workspace = self._paths["workspace"]
        venv_pip = runtime / "venv" / "Scripts" / "pip.exe"
        requirements = runtime / "requirements.txt"
        dev_seosoyoung = workspace / "seosoyoung"

        # runtime git pull
        logger.info("업데이트: runtime git pull")
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=str(runtime),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("runtime git pull 실패, stash 재시도")
            subprocess.run(["git", "stash"], cwd=str(runtime))
            subprocess.run(["git", "pull", "origin", "main"], cwd=str(runtime))
            subprocess.run(["git", "stash", "pop"], cwd=str(runtime))

        # pip install
        if requirements.exists():
            logger.info("업데이트: pip install")
            subprocess.run(
                [str(venv_pip), "install", "-r", str(requirements), "--quiet"],
                cwd=str(runtime),
            )

        # 개발 소스 동기화
        if dev_seosoyoung.exists():
            logger.info("업데이트: seosoyoung 개발 소스 동기화")
            subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(dev_seosoyoung),
            )

        logger.info("업데이트 완료")

    def status(self) -> dict:
        """현재 배포 상태 반환 (대시보드용)."""
        return {
            "state": self._state.value,
        }
