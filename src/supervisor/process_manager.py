"""ProcessManager - 자식 프로세스 생명주기 관리"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from .models import (
    ExitAction,
    EXIT_CODE_ACTIONS,
    DEFAULT_EXIT_ACTION,
    ProcessConfig,
    ProcessState,
    ProcessStatus,
)

logger = logging.getLogger("supervisor")


class ProcessManager:
    """프로세스 시작/중지/재시작/상태 관리"""

    def __init__(self) -> None:
        self._states: dict[str, ProcessState] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._log_files: dict[str, tuple] = {}  # name → (stdout_fh, stderr_fh)

    def register(self, config: ProcessConfig) -> None:
        """프로세스 설정 등록"""
        if config.name in self._states:
            raise ValueError(f"이미 등록된 프로세스: {config.name}")
        self._states[config.name] = ProcessState(config=config)

    def _ensure_registered(self, name: str) -> ProcessState:
        state = self._states.get(name)
        if state is None:
            raise KeyError(f"등록되지 않은 프로세스: {name}")
        return state

    def _open_log_files(self, config: ProcessConfig):
        """로그 파일 핸들 열기"""
        stdout_path = config.stdout_log
        stderr_path = config.stderr_log
        if stdout_path is None or stderr_path is None:
            return None, None

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_fh = open(stdout_path, "a", encoding="utf-8")
        stderr_fh = open(stderr_path, "a", encoding="utf-8")
        self._log_files[config.name] = (stdout_fh, stderr_fh)
        return stdout_fh, stderr_fh

    def _close_log_files(self, name: str) -> None:
        """로그 파일 핸들 닫기"""
        fhs = self._log_files.pop(name, None)
        if fhs is not None:
            for fh in fhs:
                try:
                    fh.close()
                except Exception:
                    pass

    def start(self, name: str) -> None:
        """프로세스 시작"""
        state = self._ensure_registered(name)
        if state.status == ProcessStatus.RUNNING:
            logger.warning("%s: 이미 실행 중 (pid=%s)", name, state.pid)
            return

        config = state.config
        env = {**os.environ, **config.env}
        cmd = [config.command, *config.args]
        cwd = config.cwd

        stdout_fh, stderr_fh = self._open_log_files(config)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=stdout_fh or subprocess.DEVNULL,
                stderr=stderr_fh or subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                ) if os.name == "nt" else 0,
            )
        except Exception:
            self._close_log_files(name)
            state.status = ProcessStatus.DEAD
            logger.exception("%s: 시작 실패", name)
            raise

        self._procs[name] = proc
        state.pid = proc.pid
        state.status = ProcessStatus.RUNNING
        logger.info("%s: 시작됨 (pid=%d)", name, proc.pid)

    def stop(self, name: str, timeout: float = 10.0) -> int | None:
        """프로세스 중지. 종료 코드 반환 (이미 중지된 경우 None)."""
        state = self._ensure_registered(name)
        proc = self._procs.get(name)

        if proc is None or state.status == ProcessStatus.STOPPED:
            return None

        logger.info("%s: 종료 요청 (pid=%s)", name, state.pid)
        try:
            proc.terminate()
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("%s: terminate 타임아웃, kill 시도", name)
            proc.kill()
            exit_code = proc.wait(timeout=5)

        self._close_log_files(name)
        state.status = ProcessStatus.STOPPED
        state.last_exit_code = exit_code
        state.pid = None
        self._procs.pop(name, None)
        logger.info("%s: 종료됨 (exit_code=%s)", name, exit_code)
        return exit_code

    def restart(self, name: str) -> None:
        """프로세스 재시작"""
        state = self._ensure_registered(name)
        state.status = ProcessStatus.RESTARTING
        state.restart_count += 1
        self.stop(name)
        self.start(name)

    def poll(self, name: str) -> int | None:
        """프로세스 상태 폴링. 종료 *직후*에만 exit code 반환, 그 외 None.

        이미 처리된(proc이 제거된) 프로세스는 None을 반환하여
        메인 루프에서 중복 처리하지 않도록 합니다.
        """
        self._ensure_registered(name)
        proc = self._procs.get(name)

        if proc is None:
            return None

        exit_code = proc.poll()
        if exit_code is not None:
            state = self._states[name]
            self._close_log_files(name)
            state.status = ProcessStatus.STOPPED
            state.last_exit_code = exit_code
            state.pid = None
            self._procs.pop(name, None)
            logger.info("%s: 자체 종료 (exit_code=%d)", name, exit_code)
        return exit_code

    def is_running(self, name: str) -> bool:
        """프로세스 실행 중 여부"""
        state = self._states.get(name)
        if state is None:
            return False
        proc = self._procs.get(name)
        if proc is None:
            return False
        return proc.poll() is None

    def status(self) -> dict[str, dict]:
        """전체 프로세스 상태 반환"""
        result = {}
        for name, state in self._states.items():
            # poll을 통해 최신 상태 반영
            self.poll(name)
            result[name] = {
                "name": name,
                "status": state.status.value,
                "pid": state.pid,
                "restart_count": state.restart_count,
                "last_exit_code": state.last_exit_code,
            }
        return result

    def resolve_exit_action(self, exit_code: int | None) -> ExitAction:
        """exit code를 ExitAction으로 변환"""
        if exit_code is None:
            return DEFAULT_EXIT_ACTION
        return EXIT_CODE_ACTIONS.get(exit_code, DEFAULT_EXIT_ACTION)

    def stop_all(self, timeout: float = 10.0) -> None:
        """등록된 모든 프로세스 종료"""
        for name in list(self._states.keys()):
            try:
                self.stop(name, timeout=timeout)
            except Exception:
                logger.exception("%s: 종료 중 오류", name)

    @property
    def registered_names(self) -> list[str]:
        return list(self._states.keys())
