"""데이터 모델: ProcessConfig, ProcessState, ExitAction"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


class ProcessStatus(enum.Enum):
    """프로세스 상태"""
    STOPPED = "stopped"
    RUNNING = "running"
    RESTARTING = "restarting"
    DEAD = "dead"


class ExitAction(enum.Enum):
    """exit code에 따른 동작"""
    SHUTDOWN = "shutdown"       # 정상 종료 (exit 0)
    UPDATE = "update"           # 업데이트 후 재시작 (exit 42)
    RESTART = "restart"         # 즉시 재시작 (exit 43)
    RESTART_DELAY = "restart_delay"  # 지연 후 재시작 (기타)


# exit code → 동작 매핑
EXIT_CODE_ACTIONS: dict[int, ExitAction] = {
    0: ExitAction.SHUTDOWN,
    42: ExitAction.UPDATE,
    43: ExitAction.RESTART,
}

DEFAULT_EXIT_ACTION = ExitAction.RESTART_DELAY
RESTART_DELAY_SECONDS = 5.0


@dataclass
class RestartPolicy:
    """재시작 정책"""
    use_exit_codes: bool = False
    auto_restart: bool = True
    restart_delay: float = RESTART_DELAY_SECONDS
    max_restarts: int = 0  # 0 = 무제한


@dataclass
class ProcessConfig:
    """프로세스 설정"""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    restart_policy: RestartPolicy = field(default_factory=RestartPolicy)
    log_dir: str | None = None
    port: int | None = None  # 프로세스가 바인딩하는 포트 (시작 전 좀비 정리용)

    @property
    def log_path(self) -> Path | None:
        if self.log_dir is None:
            return None
        return Path(self.log_dir)

    @property
    def stdout_log(self) -> Path | None:
        p = self.log_path
        if p is None:
            return None
        return p / f"{self.name}-out.log"

    @property
    def stderr_log(self) -> Path | None:
        p = self.log_path
        if p is None:
            return None
        return p / f"{self.name}-error.log"


@dataclass
class ProcessState:
    """프로세스 런타임 상태"""
    config: ProcessConfig
    status: ProcessStatus = ProcessStatus.STOPPED
    pid: int | None = None
    restart_count: int = 0
    last_exit_code: int | None = None
