"""Deployer - 배포 상태 머신"""

from __future__ import annotations

import enum
import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .notifier import (
    notify_deploy_start,
    notify_deploy_success,
    notify_deploy_failure,
    notify_change_detected,
    notify_waiting_sessions,
)

if TYPE_CHECKING:
    from .process_manager import ProcessManager
    from .session_monitor import SessionMonitor

logger = logging.getLogger("supervisor")

# supervisor 코드가 포함된 경로 접두사
_SUPERVISOR_PATH_PREFIX = "src/supervisor/"

# waiting_sessions 상태 최대 대기 시간 (초)
_WAITING_SESSIONS_TIMEOUT = 600  # 10분


class SupervisorRestartRequired(Exception):
    """supervisor 자체 코드 변경으로 프로세스 재시작이 필요할 때 발생."""


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
        self._waiting_since: float | None = None
        self._webhook_config = paths["runtime"] / "data" / "watchdog_config.json"

    @property
    def state(self) -> DeployState:
        return self._state

    def notify_change(self) -> None:
        """git 변경 감지 알림. idle이면 pending으로 전환."""
        if self._state == DeployState.IDLE:
            self._state = DeployState.PENDING
            logger.info("배포 상태: idle → pending")
            try:
                notify_change_detected(self._paths, self._webhook_config)
            except Exception:
                logger.exception("변경 감지 알림 전송 실패")

    def tick(self) -> None:
        """상태 머신 한 스텝 진행."""
        if self._state == DeployState.IDLE:
            return

        if self._state in (DeployState.PENDING, DeployState.WAITING_SESSIONS):
            timed_out = False
            if self._state == DeployState.WAITING_SESSIONS:
                if self._waiting_since is None:
                    self._waiting_since = time.monotonic()
                elapsed = time.monotonic() - self._waiting_since
                if elapsed >= _WAITING_SESSIONS_TIMEOUT:
                    logger.warning(
                        "세션 대기 타임아웃 (%.0f초 경과), 강제 배포 진행", elapsed,
                    )
                    timed_out = True

            if self._session_monitor.is_safe_to_deploy() or timed_out:
                self._state = DeployState.DEPLOYING
                self._waiting_since = None
                logger.info("배포 상태: → deploying (세션 0 또는 타임아웃)")
                try:
                    self._execute_deploy()
                finally:
                    self._state = DeployState.IDLE
            elif self._state == DeployState.PENDING:
                self._state = DeployState.WAITING_SESSIONS
                self._waiting_since = time.monotonic()
                logger.info("배포 상태: pending → waiting_sessions (세션 대기)")
                try:
                    notify_waiting_sessions(self._webhook_config)
                except Exception:
                    logger.exception("세션 대기 알림 전송 실패")

    def _get_changed_files(self) -> list[str]:
        """원격 대비 변경된 파일 목록을 가져온다."""
        runtime = self._paths["runtime"]
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD..origin/main"],
                cwd=str(runtime),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.warning("git diff 실패: %s", result.stderr.strip())
                return []
            return [f for f in result.stdout.strip().split("\n") if f]
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("변경 파일 목록 조회 실패: %s", exc)
            return []

    def _has_supervisor_changes(self, changed_files: list[str]) -> bool:
        """변경 파일 중 supervisor 코드가 포함되어 있는지 확인."""
        return any(f.startswith(_SUPERVISOR_PATH_PREFIX) for f in changed_files)

    def _execute_deploy(self) -> None:
        """배포 실행: stop → update → restart.

        supervisor 자체 코드 변경이 감지되면 SupervisorRestartRequired를 발생시켜
        watchdog이 pull 후 supervisor를 재시작하도록 한다.
        """
        changed_files = self._get_changed_files()
        supervisor_changed = self._has_supervisor_changes(changed_files)

        if supervisor_changed:
            logger.info("supervisor 코드 변경 감지 → 자식 프로세스 중지 후 exit 42")
            self._pm.stop_all()
            raise SupervisorRestartRequired()

        # 배포 시작 알림 (실패해도 배포는 계속)
        try:
            notify_deploy_start(self._paths, self._webhook_config)
        except Exception:
            logger.exception("배포 시작 알림 전송 실패 (배포는 계속)")

        try:
            logger.info("배포 시작: 프로세스 중지")
            self._pm.stop_all()

            logger.info("배포: 업데이트 수행")
            self._do_update()

            logger.info("배포: 프로세스 재시작")
            for name in self._pm.registered_names:
                self._pm.start(name)

            logger.info("배포 완료")

            # 배포 성공 알림
            try:
                notify_deploy_success(self._webhook_config)
            except Exception:
                logger.exception("배포 성공 알림 전송 실패")
        except Exception as exc:
            logger.exception("배포 실패, 프로세스 재시작 시도")

            # 배포 실패 알림
            try:
                notify_deploy_failure(self._webhook_config, error=str(exc))
            except Exception:
                logger.exception("배포 실패 알림 전송 실패")

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
