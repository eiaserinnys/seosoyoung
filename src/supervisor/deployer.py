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

# soulstream 관련 경로 접두사
_SOULSTREAM_DASHBOARD_PATH_PREFIX = "soul-dashboard/"
_SOULSTREAM_DASHBOARD_PACKAGE_LOCK = "soul-dashboard/package-lock.json"
_SOULSTREAM_SERVER_PATH_PREFIX = "soul-server/"

# 배포 시 프로세스 stop() 타임아웃 (초)
# 0 = 무한 대기 (클로드 세션이 자연 종료될 때까지 기다림)
_DEPLOY_STOP_TIMEOUT = 0

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
        monitored_repos: dict[str, Path] | None = None,
    ) -> None:
        self._pm = process_manager
        self._session_monitor = session_monitor
        self._paths = paths
        self._monitored_repos: dict[str, Path] = (
            dict(monitored_repos) if monitored_repos else {}
        )
        self._state = DeployState.IDLE
        self._pending_sources: set[str] = set()
        self._waiting_since: float | None = None
        self._webhook_config = paths["runtime"] / "data" / "watchdog_config.json"

    @property
    def state(self) -> DeployState:
        return self._state

    def notify_change(self, source: str = "runtime") -> None:
        """git 변경 감지 알림. idle이면 pending으로 전환.

        이미 PENDING/WAITING_SESSIONS 상태라면 source를 누적만 한다.
        _do_update()는 모든 리포를 일괄 pull하므로 누락은 없지만,
        로깅에서 어느 리포들이 변경되었는지 정확히 추적할 수 있다.
        """
        self._pending_sources.add(source)
        if self._state == DeployState.IDLE:
            self._state = DeployState.PENDING
            logger.info("배포 상태: idle → pending (source: %s)", source)
            try:
                notify_change_detected(
                    self._monitored_repos, self._webhook_config,
                )
            except Exception:
                logger.exception("변경 감지 알림 전송 실패")
        else:
            logger.info(
                "변경 감지 누적: source=%s (현재 상태: %s, 누적: %s)",
                source, self._state.value, self._pending_sources,
            )

    def tick(self) -> None:
        """상태 머신 한 스텝 진행."""
        if self._state == DeployState.IDLE:
            return

        if self._state in (DeployState.PENDING, DeployState.WAITING_SESSIONS):
            if self._session_monitor.is_safe_to_deploy():
                self._state = DeployState.DEPLOYING
                self._waiting_since = None
                # 배포 시작 전 누적 sources를 비운다.
                # 배포 중 새로 들어오는 notify_change()는 다시 누적된다.
                self._pending_sources.clear()
                logger.info("배포 상태: → deploying (활성 세션 없음)")
                try:
                    self._execute_deploy()
                finally:
                    if self._pending_sources:
                        # 배포 중 추가 변경이 감지됨 → 재배포 예약
                        logger.info(
                            "배포 중 누적된 변경 감지, 재배포 예약: %s",
                            self._pending_sources,
                        )
                        self._state = DeployState.PENDING
                    else:
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

        # seosoyoung-plugins 동기화
        dev_plugins = workspace / ".projects" / "seosoyoung-plugins"
        if dev_plugins.exists():
            plugins_old_head = self._get_repo_head(dev_plugins)

            logger.info("업데이트: seosoyoung-plugins 동기화")
            pull_result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(dev_plugins),
                capture_output=True,
                text=True,
            )
            if pull_result.returncode != 0:
                logger.warning(
                    "seosoyoung-plugins git pull 실패 (rc=%d): %s, stash 재시도",
                    pull_result.returncode,
                    pull_result.stderr.strip()[:500],
                )
                subprocess.run(["git", "stash"], cwd=str(dev_plugins))
                subprocess.run(
                    ["git", "pull", "origin", "main"], cwd=str(dev_plugins),
                )
                subprocess.run(["git", "stash", "pop"], cwd=str(dev_plugins))

            plugins_new_head = self._get_repo_head(dev_plugins)

            # 변경이 있을 때만 editable install 갱신 (의존성 변경 반영)
            if (
                plugins_old_head
                and plugins_new_head
                and plugins_old_head != plugins_new_head
                and venv_pip.exists()
            ):
                logger.info("업데이트: seosoyoung-plugins pip install -e")
                pip_result = subprocess.run(
                    [str(venv_pip), "install", "-e", str(dev_plugins), "--quiet"],
                    cwd=str(runtime),
                    capture_output=True,
                    text=True,
                )
                if pip_result.returncode != 0:
                    logger.warning(
                        "seosoyoung-plugins pip install 실패 (rc=%d): %s",
                        pip_result.returncode,
                        pip_result.stderr.strip()[:500],
                    )

        # soulstream 리포 동기화 (soulstream_runtime이 git repo)
        soulstream_dir = self._paths["soulstream_runtime"]
        if soulstream_dir.exists():
            old_head = self._get_repo_head(soulstream_dir)

            logger.info("업데이트: soulstream 소스 동기화")
            pull_result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(soulstream_dir),
                capture_output=True,
                text=True,
            )
            if pull_result.returncode != 0:
                logger.warning(
                    "soulstream git pull 실패 (rc=%d): %s, stash 재시도",
                    pull_result.returncode,
                    pull_result.stderr.strip()[:500],
                )
                subprocess.run(["git", "stash"], cwd=str(soulstream_dir))
                retry_result = subprocess.run(
                    ["git", "pull", "origin", "main"],
                    cwd=str(soulstream_dir),
                    capture_output=True,
                    text=True,
                )
                if retry_result.returncode != 0:
                    # stash로도 해결 안 되면 강제 리셋
                    logger.warning(
                        "soulstream stash 후에도 pull 실패, reset --hard 수행"
                    )
                    subprocess.run(
                        ["git", "reset", "--hard", "origin/main"],
                        cwd=str(soulstream_dir),
                    )
                else:
                    subprocess.run(["git", "stash", "pop"], cwd=str(soulstream_dir))

            new_head = self._get_repo_head(soulstream_dir)

            if old_head and new_head and old_head != new_head:
                changed = self._get_changed_files_between(
                    soulstream_dir, old_head, new_head,
                )

                # soul-server 변경 시 pip install + editable pth 보정
                if any(f.startswith(_SOULSTREAM_SERVER_PATH_PREFIX) for f in changed):
                    packages_file = soulstream_dir / "soul-server" / "packages.txt"
                    if packages_file.exists():
                        soulstream_pip = soulstream_dir / "venv" / "Scripts" / "pip.exe"
                        if soulstream_pip.exists():
                            logger.info("soulstream: pip install (packages.txt)")
                            pip_result = subprocess.run(
                                [str(soulstream_pip), "install", "-r",
                                 str(packages_file), "--quiet"],
                                cwd=str(soulstream_dir / "soul-server"),
                                capture_output=True,
                                text=True,
                            )
                            if pip_result.returncode != 0:
                                logger.warning(
                                    "soulstream pip install 실패 (rc=%d): %s",
                                    pip_result.returncode,
                                    pip_result.stderr.strip()[:500],
                                )
                    # hatchling editable install 버그 보정 (pip install 결과와 무관)
                    self._fix_editable_pth(soulstream_dir)

                # soulstream-dashboard 변경 시 npm install
                if any(f.startswith(_SOULSTREAM_DASHBOARD_PATH_PREFIX) for f in changed):
                    needs_install = any(
                        f == _SOULSTREAM_DASHBOARD_PACKAGE_LOCK for f in changed
                    )
                    dashboard_dir = soulstream_dir / "soul-dashboard"
                    build_ok = self._build_soul_dashboard(
                        dashboard_dir, npm_install=needs_install,
                    )
                    if not build_ok:
                        logger.warning(
                            "soulstream-dashboard 빌드 실패, "
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
    def _fix_editable_pth(soulstream_dir: Path) -> None:
        """hatchling editable install이 빈 .pth 파일을 생성하는 버그를 보정한다.

        soul-server의 src/ 디렉토리를 가리키는 경로가 .pth 파일에 있어야
        soul_server 모듈을 import할 수 있다.
        """
        site_packages = soulstream_dir / "venv" / "Lib" / "site-packages"
        pth_file = site_packages / "_soul_server.pth"
        expected_path = str(soulstream_dir / "soul-server" / "src")

        if not pth_file.exists():
            return

        try:
            content = pth_file.read_text(encoding="utf-8").strip()
            if content == expected_path:
                return
            if not content:
                logger.warning("soulstream: _soul_server.pth가 비어있음 → 보정")
            else:
                logger.info("soulstream: _soul_server.pth 보정 (%r → %s)", content, expected_path)
            pth_file.write_text(expected_path + "\n", encoding="utf-8")
        except OSError:
            logger.exception("_soul_server.pth 보정 실패")

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
        info: dict = {"state": self._state.value}
        if self._waiting_since is not None:
            info["waiting_seconds"] = round(
                time.monotonic() - self._waiting_since,
            )
        return info
