"""supervisor 진입점 - 메인 루프"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import build_process_configs, _resolve_paths
from .models import ExitAction, RESTART_DELAY_SECONDS, ProcessStatus
from .process_manager import ProcessManager

logger = logging.getLogger("supervisor")

HEALTH_CHECK_INTERVAL = 5.0  # 초


def _setup_logging() -> None:
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] supervisor: [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _do_update(paths: dict[str, Path]) -> None:
    """업데이트 수행: git pull + pip install (wrapper.py 로직 이관)"""
    runtime = paths["runtime"]
    workspace = paths["workspace"]
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
    while not shutting_down:
        time.sleep(HEALTH_CHECK_INTERVAL)

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
                _do_update(paths)
                pm.restart(name)
            elif action == ExitAction.RESTART:
                pm.restart(name)
            elif action == ExitAction.RESTART_DELAY:
                delay = policy.restart_delay or RESTART_DELAY_SECONDS
                logger.info("%s: %.1f초 후 재시작", name, delay)
                time.sleep(delay)
                pm.restart(name)


if __name__ == "__main__":
    main()
