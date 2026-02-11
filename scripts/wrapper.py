#!/usr/bin/env python3
"""
wrapper.py - 봇 프로세스 관리
exit code에 따라 재시작/업데이트 처리

Exit codes:
    0  - 정상 종료 (wrapper도 종료)
    42 - 업데이트 요청 (git pull + pip install + 재시작)
    43 - 재시작 요청 (즉시 재시작)
    기타 - 비정상 종료 (5초 후 재시작)
"""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# 경로 설정
SCRIPT_DIR = Path(__file__).parent.resolve()
RUNTIME_DIR = SCRIPT_DIR.parent  # seosoyoung_runtime
SOYOUNG_ROOT = RUNTIME_DIR.parent  # soyoung_root
WORKSPACE_DIR = SOYOUNG_ROOT / "slackbot_workspace"
LOGS_DIR = RUNTIME_DIR / "logs"
VENV_PYTHON = RUNTIME_DIR / "venv" / "Scripts" / "python.exe"
VENV_PIP = RUNTIME_DIR / "venv" / "Scripts" / "pip.exe"
REQUIREMENTS_FILE = RUNTIME_DIR / "requirements.txt"
DEV_SEOSOYOUNG = WORKSPACE_DIR / "seosoyoung"
REPO_URL = "https://github.com/eias/seosoyoung"


def log(message: str, level: str = "INFO") -> None:
    """로그 출력"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] wrapper: [{level}] {message}", flush=True)


def run_command(cmd: list[str], cwd: Path | None = None) -> int:
    """명령어 실행 후 exit code 반환"""
    log(f"명령어 실행: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def git_pull_with_stash(cwd: Path, label: str) -> bool:
    """git pull 수행. 실패 시 stash → pull → stash pop으로 재시도. 성공 여부 반환."""
    exit_code = run_command(["git", "pull", "origin", "main"], cwd=cwd)
    if exit_code == 0:
        return True

    log(f"{label} git pull 실패 - stash 후 재시도", "WARN")
    run_command(["git", "stash"], cwd=cwd)
    exit_code = run_command(["git", "pull", "origin", "main"], cwd=cwd)
    run_command(["git", "stash", "pop"], cwd=cwd)

    if exit_code != 0:
        log(f"{label} git pull 재시도 실패", "ERROR")
        return False
    return True


def sync_dev_seosoyoung() -> None:
    """slackbot_workspace/seosoyoung 개발용 소스 동기화"""
    if not DEV_SEOSOYOUNG.exists():
        log("seosoyoung 개발 소스 클론 중...")
        exit_code = run_command(["git", "clone", REPO_URL, str(DEV_SEOSOYOUNG)])
        if exit_code == 0:
            log("seosoyoung 클론 완료")
        else:
            log("seosoyoung 클론 실패", "ERROR")
    else:
        log("seosoyoung 개발 소스 동기화 중...")
        if git_pull_with_stash(DEV_SEOSOYOUNG, "seosoyoung"):
            log("seosoyoung 동기화 완료")
        else:
            log("seosoyoung 동기화 실패", "WARN")


def do_update() -> None:
    """업데이트 수행: git pull + pip install"""
    log("업데이트 요청 - git pull 실행")

    # runtime 폴더에서 git pull (실패 시 stash 재시도)
    if not git_pull_with_stash(RUNTIME_DIR, "runtime"):
        log("runtime 업데이트 실패 - 깨진 상태로 진행하지 않음", "ERROR")
        return

    # 의존성 설치
    if REQUIREMENTS_FILE.exists():
        log("의존성 설치 중...")
        exit_code = run_command(
            [str(VENV_PIP), "install", "-r", str(REQUIREMENTS_FILE), "--quiet"],
            cwd=RUNTIME_DIR
        )
        if exit_code == 0:
            log("의존성 설치 완료")
        else:
            log("의존성 설치 실패 (계속 진행)", "WARN")

    # 개발 소스 동기화
    sync_dev_seosoyoung()
    log("업데이트 완료, 재시작...")


def run_bot() -> int:
    """봇 실행 후 exit code 반환"""
    log("봇 시작...")

    # 환경 변수 설정
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(RUNTIME_DIR / "src")

    # 봇 실행
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "seosoyoung.main"],
        cwd=WORKSPACE_DIR,
        env=env
    )

    return result.returncode


def main() -> None:
    """메인 루프"""
    # 로그 폴더 생성
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 작업 폴더 생성
    if not WORKSPACE_DIR.exists():
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        log(f"작업 폴더 생성: {WORKSPACE_DIR}")

    log("=" * 40)
    log("시작")
    log("=" * 40)
    log(f"작업 폴더: {WORKSPACE_DIR}")
    log(f"런타임 폴더: {RUNTIME_DIR}")

    # 초기 동기화
    sync_dev_seosoyoung()

    while True:
        exit_code = run_bot()
        log(f"봇 종료 (exit code: {exit_code})")

        if exit_code == 0:
            log("정상 종료")
            break
        elif exit_code == 42:
            do_update()
            # 재시작을 위해 루프 계속
        elif exit_code == 43:
            log("재시작 요청")
            # 즉시 재시작
        else:
            log(f"비정상 종료, 5초 후 재시작...", "ERROR")
            time.sleep(5)

    log("=" * 40)
    log("종료")
    log("=" * 40)


if __name__ == "__main__":
    main()
