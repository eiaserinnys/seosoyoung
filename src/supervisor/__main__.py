"""supervisor 진입점 - 메인 루프"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from . import job_object
from .config import build_process_configs, _resolve_paths
from .dashboard import create_app, _RestartState
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
    session_monitor: SessionMonitor,
    log_dir: Path,
    restart_state: _RestartState,
) -> None:
    """대시보드 서버를 데몬 스레드로 실행."""
    import uvicorn

    app = create_app(
        process_manager=pm,
        deployer=deployer,
        git_poller=git_poller,
        session_monitor=session_monitor,
        log_dir=log_dir,
        restart_state=restart_state,
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


def _load_env() -> None:
    """workspace의 .env 파일을 로드하여 환경변수에 반영.

    모든 환경변수는 workspace/.env에 통합되어 있다.
    supervisor가 로드한 값은 os.environ에 반영되어
    non-Python 자식 프로세스(node, Go)에게도 상속된다.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("python-dotenv가 설치되지 않아 .env 로딩을 건너뜁니다")
        return

    paths = _resolve_paths()
    env_file = paths["workspace"] / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
        logger.info(".env 로드 완료: %s", env_file)
    else:
        logger.warning(".env 파일을 찾을 수 없습니다: %s", env_file)


def main() -> None:
    """메인 루프"""
    _setup_logging()
    _load_env()

    paths = _resolve_paths()
    paths["logs"].mkdir(parents=True, exist_ok=True)

    logger.info("=" * 40)
    logger.info("supervisor 시작")
    logger.info("=" * 40)

    # Job Object 생성: supervisor 종료 시 모든 자식 프로세스 자동 정리
    job_object.create_job_object()

    pm = ProcessManager()
    configs = build_process_configs()
    for cfg in configs:
        pm.register(cfg)

    # 전체 시작 (개별 실패가 supervisor를 죽이지 않도록 보호)
    for name in pm.registered_names:
        try:
            pm.start(name)
        except Exception:
            logger.exception("%s: 초기 시작 실패, 메인 루프에서 재시도 예정", name)

    # GitPoller: runtime 리포 변경 감지
    # (deployer 생성 전이지만, restart marker 확인을 위해 paths를 사용)
    git_poller = GitPoller(
        repo_path=paths["runtime"],
        remote="origin",
        branch="main",
    )

    # GitPoller: soulstream 리포 변경 감지
    soulstream_poller: GitPoller | None = None
    if paths["soulstream"].is_dir():
        soulstream_poller = GitPoller(
            repo_path=paths["soulstream"],
            remote="origin",
            branch="main",
        )
        logger.info("soulstream git poller 활성화: %s", paths["soulstream"])

    # SessionMonitor: 봇 자식 프로세스 중 Claude Code 세션 감지
    session_monitor = SessionMonitor(process_manager=pm)

    # Deployer: 배포 상태 머신
    deployer = Deployer(
        process_manager=pm,
        session_monitor=session_monitor,
        paths=paths,
    )

    # 재시작 마커 확인: 이전 supervisor가 exit 42로 재시작한 경우 완료 알림 전송
    deployer.check_and_notify_restart_complete()

    # 재기동 상태 (대시보드 ↔ 메인 루프 통신)
    restart_state = _RestartState()

    # 대시보드 (FastAPI + uvicorn, 백그라운드 스레드)
    _start_dashboard(
        pm, deployer, git_poller, session_monitor,
        paths["logs"], restart_state,
    )

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
    EXIT_CODE_SUPERVISOR_RESTART = 42      # git pull 후 재시작 (watchdog이 처리)
    EXIT_CODE_SUPERVISOR_PLAIN_RESTART = 44  # supervisor 전체 재시작 (watchdog이 처리)
    exiting_intentionally = False  # sys.exit() 호출 시 finally 중복 방지
    last_git_check = 0.0

    try:
        while not shutting_down:
            time.sleep(HEALTH_CHECK_INTERVAL)

            # 대시보드에서 재기동 요청이 왔는지 확인
            if restart_state.restart_requested.is_set():
                logger.info("대시보드에서 supervisor 재기동 요청 수신")
                deployer.notify_and_mark_restart()
                exiting_intentionally = True
                pm.stop_all()
                job_object.close_job_object()
                sys.exit(EXIT_CODE_SUPERVISOR_PLAIN_RESTART)

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
                    # exit code 43: 해당 프로세스만 재시작
                    logger.info("%s: exit 43 → 프로세스만 재시작", name)
                    pm.restart(name)
                elif action == ExitAction.RESTART_SUPERVISOR:
                    # exit code 44: supervisor 전체 재시작 (watchdog으로 위임)
                    logger.info(
                        "%s: exit 44 → supervisor 전체 재시작",
                        name,
                    )
                    deployer.notify_and_mark_restart()
                    exiting_intentionally = True
                    pm.stop_all()
                    job_object.close_job_object()
                    sys.exit(EXIT_CODE_SUPERVISOR_PLAIN_RESTART)
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
                if soulstream_poller is not None and soulstream_poller.check():
                    deployer.notify_change(source="soulstream")

            # Deployer tick (세션 대기 → 배포 진행)
            deployer.tick()

    except SupervisorRestartRequired:
        logger.info("supervisor 자체 코드 변경 감지 → exit %d", EXIT_CODE_SUPERVISOR_RESTART)
        exiting_intentionally = True
        pm.stop_all()
        job_object.close_job_object()
        sys.exit(EXIT_CODE_SUPERVISOR_RESTART)
    finally:
        # 비정상 종료(unhandled exception) 시에도 자식 프로세스 정리 시도.
        # Job Object의 KILL_ON_JOB_CLOSE가 최종 안전장치 역할을 하지만,
        # 가능하면 graceful shutdown을 시도한다.
        if not shutting_down and not exiting_intentionally:
            logger.warning("예기치 않은 종료, 자식 프로세스 정리 중")
            pm.stop_all()
            job_object.close_job_object()


if __name__ == "__main__":
    main()
