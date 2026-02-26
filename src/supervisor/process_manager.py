"""ProcessManager - 자식 프로세스 생명주기 관리"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from . import job_object
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

    def _kill_port_holder(self, port: int) -> None:
        """지정된 포트를 점유 중인 프로세스를 강제 종료한다 (Windows 전용)."""
        if os.name != "nt":
            return
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5,
            )
            my_pid = os.getpid()
            known_pids = {
                p.pid for p in self._procs.values() if p.poll() is None
            }
            for line in result.stdout.splitlines():
                if "LISTENING" not in line:
                    continue
                if f"127.0.0.1:{port}" not in line and f"0.0.0.0:{port}" not in line:
                    continue
                parts = line.split()
                pid = int(parts[-1])
                if pid == my_pid:
                    logger.warning("포트 %d: supervisor 자신 (PID %d), 건너뜀", port, pid)
                    continue
                if pid in known_pids:
                    logger.warning("포트 %d: 관리 중인 프로세스 (PID %d), 건너뜀", port, pid)
                    continue
                logger.warning("포트 %d 점유 프로세스 종료: PID %d", port, pid)
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
                time.sleep(0.5)
                break
        except Exception:
            logger.debug("포트 %d 정리 중 오류 (무시)", port, exc_info=True)

    def start(self, name: str) -> None:
        """프로세스 시작"""
        state = self._ensure_registered(name)
        if state.status == ProcessStatus.RUNNING:
            logger.warning("%s: 이미 실행 중 (pid=%s)", name, state.pid)
            return

        config = state.config

        # 포트 좀비 정리
        if config.port is not None:
            self._kill_port_holder(config.port)

        cmd = [config.command, *config.args]
        cwd = config.cwd

        stdout_fh, stderr_fh = self._open_log_files(config)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
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

        # Job Object에 등록 (supervisor 종료 시 자식도 함께 종료)
        if job_object.assign_process(proc):
            logger.debug("%s: Job Object에 등록됨 (pid=%d)", name, proc.pid)

        self._procs[name] = proc
        state.pid = proc.pid
        state.status = ProcessStatus.RUNNING
        logger.info("%s: 시작됨 (pid=%d)", name, proc.pid)

    def _request_graceful_shutdown(self, url: str, timeout: float = 3.0) -> bool:
        """HTTP POST로 graceful shutdown 요청. 성공 시 True."""
        import urllib.request
        try:
            req = urllib.request.Request(url, method="POST", data=b"")
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception as e:
            logger.debug("Graceful shutdown 요청 실패 (%s): %s", url, e)
            return False

    def _kill_process_tree(self, pid: int) -> None:
        """프로세스와 모든 자손을 강제 종료 (psutil)."""
        import psutil
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            # 모든 프로세스가 실제로 종료될 때까지 대기
            gone, alive = psutil.wait_procs(children + [parent], timeout=3)
            if alive:
                logger.warning(
                    "프로세스 트리 킬 후에도 살아있는 프로세스: %s",
                    [p.pid for p in alive],
                )
        except psutil.NoSuchProcess:
            pass

    def stop(self, name: str, timeout: float = 10.0) -> int | None:
        """프로세스 중지. 종료 코드 반환 (이미 중지된 경우 None).

        shutdown_url이 설정된 경우 HTTP graceful shutdown을 먼저 시도하고,
        실패 시 프로세스 트리 전체를 강제 종료합니다.
        """
        state = self._ensure_registered(name)
        proc = self._procs.get(name)

        if proc is None or state.status == ProcessStatus.STOPPED:
            return None

        config = state.config
        pid = proc.pid
        logger.info("%s: 종료 요청 (pid=%s)", name, pid)

        exit_code = None

        # Phase 1: Graceful shutdown via HTTP
        if config.shutdown_url:
            if self._request_graceful_shutdown(config.shutdown_url):
                logger.info("%s: graceful shutdown 요청 전송", name)
                try:
                    exit_code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("%s: graceful shutdown 타임아웃", name)

        # Phase 2: 아직 살아있으면 프로세스 트리 킬
        if exit_code is None:
            if config.shutdown_url:
                logger.warning("%s: graceful 실패, 프로세스 트리 강제 종료 (pid=%s)", name, pid)
            else:
                logger.info("%s: 프로세스 트리 종료 (pid=%s)", name, pid)
            self._kill_process_tree(pid)
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("%s: 트리 킬 후에도 종료 안됨", name)
                try:
                    proc.kill()
                    exit_code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.critical("%s: kill 후에도 종료 안됨, 좀비 가능", name)
                    exit_code = -1

        # Cleanup
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

    def get_pid(self, name: str) -> int | None:
        """등록된 프로세스의 PID 반환. 미실행 또는 미등록이면 None."""
        state = self._states.get(name)
        if state is None:
            return None
        return state.pid

    @property
    def registered_names(self) -> list[str]:
        return list(self._states.keys())
