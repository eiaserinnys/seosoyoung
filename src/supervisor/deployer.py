"""Deployer - 배포 상태 머신"""

from __future__ import annotations

import enum
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .notifier import (
    notify_deploy_start,
    notify_deploy_failure,
    notify_change_detected,
    notify_waiting_sessions,
    notify_restart_start,
    notify_restart_complete,
)

if TYPE_CHECKING:
    from .process_manager import ProcessManager
    from .session_monitor import SessionMonitor

logger = logging.getLogger("supervisor")

# supervisor 코드가 포함된 경로 접두사
_SUPERVISOR_PATH_PREFIX = "src/supervisor/"

# soul-dashboard 관련 경로 접두사
_SOUL_DASHBOARD_PATH_PREFIX = "src/soul-dashboard/"
_SOUL_DASHBOARD_PACKAGE_LOCK = "src/soul-dashboard/package-lock.json"

# waiting_sessions 상태 최대 대기 시간 (초)
_WAITING_SESSIONS_TIMEOUT = 600  # 10분

# 배포 시 프로세스 stop() 타임아웃 (초)
# 봇이 사용자 응답(팝업)을 대기할 수 있으므로 충분히 확보
_DEPLOY_STOP_TIMEOUT = 300.0  # 5분

# 재시작 마커 파일명
_RESTART_MARKER_NAME = "restart_in_progress"

# npm 빌드 타임아웃 (초)
_NPM_TIMEOUT = 120


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
            self.notify_and_mark_restart()
            self._pm.stop_all(timeout=_DEPLOY_STOP_TIMEOUT)
            raise SupervisorRestartRequired()

        # 배포 시작 알림 (실패해도 배포는 계속)
        try:
            notify_deploy_start(self._paths, self._webhook_config)
        except Exception:
            logger.exception("배포 시작 알림 전송 실패 (배포는 계속)")

        try:
            logger.info("배포 시작: 프로세스 중지")
            self._pm.stop_all(timeout=_DEPLOY_STOP_TIMEOUT)

            logger.info("배포: 업데이트 수행")
            self._do_update()

            # 재시작 시작 알림
            try:
                notify_restart_start(self._webhook_config)
            except Exception:
                logger.exception("재시작 시작 알림 전송 실패")

            logger.info("배포: 프로세스 재시작")
            for name in self._pm.registered_names:
                self._pm.start(name)

            logger.info("배포 완료")

            # 재시작 완료 알림
            try:
                notify_restart_complete(self._webhook_config)
            except Exception:
                logger.exception("재시작 완료 알림 전송 실패")
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
        """git pull + pip install + soul-dashboard 빌드."""
        runtime = self._paths["runtime"]
        workspace = self._paths["workspace"]
        venv_pip = runtime / "venv" / "Scripts" / "pip.exe"
        requirements = runtime / "requirements.txt"
        dev_seosoyoung = workspace / ".projects" / "seosoyoung"

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
            old_head = self._get_repo_head(dev_seosoyoung)

            logger.info("업데이트: seosoyoung 개발 소스 동기화")
            pull_result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(dev_seosoyoung),
                capture_output=True,
                text=True,
            )
            if pull_result.returncode != 0:
                logger.warning(
                    "seosoyoung git pull 실패 (rc=%d): %s",
                    pull_result.returncode,
                    pull_result.stderr.strip()[:500],
                )

            new_head = self._get_repo_head(dev_seosoyoung)

            # soul-dashboard 빌드 (변경 감지 시)
            if old_head and new_head and old_head != new_head:
                changed = self._get_changed_files_between(
                    dev_seosoyoung, old_head, new_head,
                )
                if self._has_soul_dashboard_changes(changed):
                    needs_install = any(
                        f == _SOUL_DASHBOARD_PACKAGE_LOCK for f in changed
                    )
                    dashboard_dir = dev_seosoyoung / "src" / "soul-dashboard"
                    build_ok = self._build_soul_dashboard(
                        dashboard_dir, npm_install=needs_install,
                    )
                    if not build_ok:
                        logger.warning(
                            "soul-dashboard 빌드 실패, "
                            "이전 빌드 결과물로 프로세스 재시작 진행",
                        )

        logger.info("업데이트 완료")

    @staticmethod
    def _get_repo_head(repo_path: Path) -> str | None:
        """리포지토리의 현재 HEAD 커밋 해시를 반환한다."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("git rev-parse 실패 (%s): %s", repo_path, exc)
        return None

    @staticmethod
    def _get_changed_files_between(
        repo_path: Path, old_ref: str, new_ref: str,
    ) -> list[str]:
        """두 커밋 사이에서 변경된 파일 목록을 반환한다."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{old_ref}..{new_ref}"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f]
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("git diff 실패 (%s): %s", repo_path, exc)
        return []

    @staticmethod
    def _has_soul_dashboard_changes(changed_files: list[str]) -> bool:
        """변경 파일 중 soul-dashboard 코드가 포함되어 있는지 확인."""
        return any(
            f.startswith(_SOUL_DASHBOARD_PATH_PREFIX) for f in changed_files
        )

    @staticmethod
    def _build_soul_dashboard(
        dashboard_dir: Path,
        *,
        npm_install: bool = False,
    ) -> bool:
        """soul-dashboard 클라이언트를 빌드한다.

        npm_install이 True이면 빌드 전에 npm install을 실행한다.
        빌드 성공 시 True, 실패 시 False를 반환한다.
        """
        npm = shutil.which("npm")
        if not npm:
            logger.warning("soul-dashboard 빌드 건너뜀: npm을 찾을 수 없음")
            return False

        if not dashboard_dir.is_dir():
            logger.warning(
                "soul-dashboard 빌드 건너뜀: 디렉토리 없음 (%s)", dashboard_dir,
            )
            return False

        cwd = str(dashboard_dir)

        if npm_install:
            logger.info("soul-dashboard: npm install")
            try:
                result = subprocess.run(
                    [npm, "install"],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=_NPM_TIMEOUT,
                )
                if result.returncode != 0:
                    logger.warning(
                        "soul-dashboard npm install 실패 (rc=%d): %s",
                        result.returncode,
                        result.stderr.strip()[:500],
                    )
                    return False
            except subprocess.TimeoutExpired:
                logger.warning("soul-dashboard npm install 타임아웃")
                return False
            except (subprocess.SubprocessError, OSError) as exc:
                logger.warning("soul-dashboard npm install 오류: %s", exc)
                return False

        logger.info("soul-dashboard: npm run build")
        try:
            result = subprocess.run(
                [npm, "run", "build"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_NPM_TIMEOUT,
            )
            if result.returncode != 0:
                logger.warning(
                    "soul-dashboard build 실패 (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip()[:500],
                )
                return False
        except subprocess.TimeoutExpired:
            logger.warning("soul-dashboard build 타임아웃")
            return False
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("soul-dashboard build 오류: %s", exc)
            return False

        logger.info("soul-dashboard 빌드 완료")
        return True

    def _create_restart_marker(self) -> None:
        """재시작 마커 파일을 생성한다.

        supervisor 자체 재시작(exit 42) 시, 새 인스턴스가 기동 후
        '재시작이 완료됐습니다' 메시지를 전송할 수 있도록 마커를 남긴다.
        """
        marker = self._paths["runtime"] / "data" / _RESTART_MARKER_NAME
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("restart", encoding="utf-8")
            logger.info("재시작 마커 파일 생성: %s", marker)
        except OSError:
            logger.exception("재시작 마커 파일 생성 실패")

    def notify_and_mark_restart(self) -> None:
        """재시작 시작 알림을 전송하고 마커 파일을 생성한다.

        supervisor 자체 재시작(exit 42/44) 전에 호출한다.
        마커 파일은 새 supervisor 인스턴스가 기동 시 '재시작이 완료됐습니다'
        메시지를 전송하기 위해 사용된다.
        """
        try:
            notify_restart_start(self._webhook_config)
        except Exception:
            logger.exception("재시작 시작 알림 전송 실패")
        self._create_restart_marker()

    def check_and_notify_restart_complete(self) -> None:
        """재시작 마커가 있으면 재시작 완료 알림을 전송하고 마커를 삭제한다.

        supervisor 기동 시 호출하여, 이전 인스턴스가 exit 42로 재시작한 경우
        '재시작이 완료됐습니다' 메시지를 보낸다.
        """
        marker = self._paths["runtime"] / "data" / _RESTART_MARKER_NAME
        if not marker.exists():
            return
        try:
            notify_restart_complete(self._webhook_config)
            marker.unlink()
            logger.info("재시작 마커 감지 → 재시작 완료 알림 전송 및 마커 삭제")
        except Exception:
            logger.exception("재시작 완료 알림 전송 실패 (마커 유지)")

    def status(self) -> dict:
        """현재 배포 상태 반환 (대시보드용)."""
        return {
            "state": self._state.value,
        }
