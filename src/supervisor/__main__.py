"""supervisor 진입점 - 메인 루프"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from .config import build_process_configs, _resolve_paths
from .dashboard import create_app
from .deployer import Deployer, SupervisorRestartRequired
from .git_poller import GitPoller
from .models import ExitAction, RESTART_DELAY_SECONDS, ProcessStatus
from .process_manager import ProcessManager
from .session_monitor import SessionMonitor

logger = logging.getLogger("supervisor")

HEALTH_CHECK_INTERVAL = 5.0  # 초
GIT_POLL_INTERVAL = 60.0  # 초
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = int(os.environ.get("SUPERVISOR_DASHBOARD_PORT", "8042"))


def _setup_logging() -> None:
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] supervisor: [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _start_dashboard(
    pm: ProcessManager,
    deployer: Deployer,
    git_poller: GitPoller,
    log_dir: Path,
) -> None:
    """대시보드 서버를 데몬 스레드로 실행."""
    import uvicorn

    app = create_app(
        process_manager=pm,
        deployer=deployer,
        git_poller=git_poller,
        log_dir=log_dir,
    )
    config = uvicorn.Config(
        app,
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    logger.info("대시보드 시작: http://%s:%d", DASHBOARD_HOST, DASHBOARD_PORT)


def main() -> None:
    """메인 루프"""
    _setup_logging()

    paths = _resolve_paths()
    paths["logs"].mkdir(parents=True, exist_ok=True)

    logger.info("=" * 40)
    logger.info("supervisor 시작")
    logger.info("=" * 40)

    pm = ProcessManager()
    configs = build_process_configs()
    for cfg in configs:
        pm.register(cfg)

    # 전체 시작
    for name in pm.registered_names:
        pm.start(name)

    # GitPoller: runtime 리포 변경 감지
    git_poller = GitPoller(
        repo_path=paths["runtime"],
        remote="origin",
        branch="main",
    )

    # SessionMonitor: Claude Code 세션 감지
    session_monitor = SessionMonitor()

    # Deployer: 배포 상태 머신
    deployer = Deployer(
        process_manager=pm,
        session_monitor=session_monitor,
        paths=paths,
    )

    # 대시보드 (FastAPI + uvicorn, 백그라운드 스레드)
    _start_dashboard(pm, deployer, git_poller, paths["logs"])

    # graceful shutdown 핸들러
    shutting_down = False

    def _on_shutdown(signum, frame):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info("시그널 수신: %s, 종료 시작", sig_name)
        pm.stop_all()
        logger.info("supervisor 종료")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_shutdown)
    signal.signal(signal.SIGINT, _on_shutdown)
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, _on_shutdown)

    # 메인 루프
    EXIT_CODE_SUPERVISOR_RESTART = 42
    last_git_check = 0.0

    try:
        while not shutting_down:
            time.sleep(HEALTH_CHECK_INTERVAL)

            # 프로세스 헬스체크
            for name in pm.registered_names:
                exit_code = pm.poll(name)
                state = pm._states[name]

                if state.status != ProcessStatus.STOPPED:
                    continue  # 아직 실행 중

                if exit_code is None:
                    continue  # poll 했지만 변화 없음 (이미 stopped)

                config = state.config
                policy = config.restart_policy

                if policy.use_exit_codes:
                    action = pm.resolve_exit_action(exit_code)
                elif policy.auto_restart:
                    action = ExitAction.RESTART_DELAY
                else:
                    action = ExitAction.SHUTDOWN

                logger.info(
                    "%s: exit_code=%s → action=%s",
                    name, exit_code, action.value,
                )

                if action == ExitAction.SHUTDOWN:
                    logger.info("%s: 정상 종료, 재시작하지 않음", name)
                elif action == ExitAction.UPDATE:
                    # exit code 42: Deployer를 통한 즉시 배포
                    deployer.notify_change()
                    deployer.tick()
                elif action == ExitAction.RESTART:
                    pm.restart(name)
                elif action == ExitAction.RESTART_DELAY:
                    delay = policy.restart_delay or RESTART_DELAY_SECONDS
                    logger.info("%s: %.1f초 후 재시작", name, delay)
                    time.sleep(delay)
                    pm.restart(name)

            # Git polling (매 GIT_POLL_INTERVAL초마다)
            now = time.monotonic()
            if now - last_git_check >= GIT_POLL_INTERVAL:
                last_git_check = now
                if git_poller.check():
                    deployer.notify_change()

            # Deployer tick (세션 대기 → 배포 진행)
            deployer.tick()

    except SupervisorRestartRequired:
        logger.info("supervisor 자체 코드 변경 감지 → exit %d", EXIT_CODE_SUPERVISOR_RESTART)
        pm.stop_all()
        sys.exit(EXIT_CODE_SUPERVISOR_RESTART)


if __name__ == "__main__":
    main()
