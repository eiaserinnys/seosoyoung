"""대시보드 - FastAPI 기반 웹 UI + REST API"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

if TYPE_CHECKING:
    from .deployer import Deployer
    from .git_poller import GitPoller
    from .process_manager import ProcessManager
    from .session_monitor import SessionMonitor

_VALID_ACTIONS = {"start", "stop", "restart"}

# 재기동 쿨다운 (초)
RESTART_COOLDOWN_SECONDS = 60.0


class RestartRequest(BaseModel):
    """POST /api/supervisor/restart 요청 바디."""
    force: bool = False


class _RestartState:
    """supervisor 재기동 상태를 추적하는 내부 클래스.

    대시보드 스레드(FastAPI)와 메인 스레드 간의 통신을 담당한다.

    NOTE: 쿨다운은 메모리에만 유지되므로, supervisor가 재시작되면 초기화된다.
    이는 의도된 동작이다. 재시작 직후에는 새 supervisor가 기동된 상태이므로
    즉시 재기동할 이유가 있을 수 있고, watchdog의 안정성 검증이 별도로 동작한다.
    """

    def __init__(self) -> None:
        self._last_restart_time: float | None = None
        self.restart_requested = threading.Event()
        self._lock = threading.Lock()

    def cooldown_remaining(self) -> float:
        """쿨다운 남은 시간(초). 0이면 쿨다운 없음."""
        with self._lock:
            if self._last_restart_time is None:
                return 0.0
            elapsed = time.monotonic() - self._last_restart_time
            remaining = RESTART_COOLDOWN_SECONDS - elapsed
            return max(0.0, remaining)

    def is_in_cooldown(self) -> bool:
        """쿨다운 중인지 여부."""
        return self.cooldown_remaining() > 0.0

    def try_mark_restart(self) -> float:
        """원자적으로 쿨다운을 확인하고, 통과하면 재기동을 마킹한다.

        Returns:
            0.0이면 재기동 수락, > 0이면 남은 쿨다운 시간(초).
        """
        with self._lock:
            if self._last_restart_time is not None:
                elapsed = time.monotonic() - self._last_restart_time
                remaining = RESTART_COOLDOWN_SECONDS - elapsed
                if remaining > 0:
                    return remaining
            self._last_restart_time = time.monotonic()
        self.restart_requested.set()
        return 0.0


def create_app(
    *,
    process_manager: ProcessManager,
    deployer: Deployer,
    git_poller: GitPoller,
    session_monitor: SessionMonitor,
    log_dir: Path,
    restart_state: _RestartState | None = None,
) -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록한다."""

    app = FastAPI(title="supervisor dashboard", docs_url=None, redoc_url=None)

    # 재기동 상태 (외부 주입 또는 내부 생성)
    _restart = restart_state or _RestartState()

    # --- API ---

    @app.get("/api/status")
    def get_status():
        return {
            "processes": process_manager.status(),
            "deploy": deployer.status(),
            "git": {
                "local_head": git_poller.local_head,
                "remote_head": git_poller.remote_head,
                "has_changes": git_poller.local_head != git_poller.remote_head,
            },
            "supervisor": {
                "cooldown_remaining": round(_restart.cooldown_remaining(), 1),
                "active_sessions_count": session_monitor.active_session_count(),
            },
        }

    @app.post("/api/process/{name}/{action}")
    def process_control(name: str, action: str):
        if action not in _VALID_ACTIONS:
            raise HTTPException(400, f"유효하지 않은 액션: {action}")
        try:
            fn = getattr(process_manager, action)
            fn(name)
        except KeyError:
            raise HTTPException(404, f"프로세스를 찾을 수 없음: {name}")
        return {"ok": True, "action": action, "process": name}

    @app.post("/api/deploy")
    def deploy_trigger():
        deployer.notify_change()
        return deployer.status()

    @app.post("/api/supervisor/restart")
    def supervisor_restart(body: RestartRequest | None = None):
        """supervisor 자체를 graceful 재기동한다.

        쿨다운 중이면 429 응답, 활성 세션이 있고 force가 아니면
        경고 응답(200)을 반환한다. 재기동이 수락되면 메인 루프에
        시그널을 보내고 watchdog이 supervisor를 재시작한다.
        """
        if body is None:
            body = RestartRequest()

        # 활성 세션 체크 (쿨다운 마킹 전에 수행하여 되돌릴 수 있게)
        active_count = session_monitor.active_session_count()
        if active_count > 0 and not body.force:
            return {
                "ok": False,
                "warning": True,
                "message": f"활성 Claude Code 세션이 {active_count}개 있습니다",
                "active_sessions_count": active_count,
            }

        # 원자적 쿨다운 체크 + 재기동 마킹 (TOCTOU 방지)
        remaining = _restart.try_mark_restart()
        if remaining > 0:
            raise HTTPException(
                429,
                detail={
                    "message": "재기동 쿨다운 중입니다",
                    "cooldown_remaining": round(remaining, 1),
                },
            )

        return {
            "ok": True,
            "message": "supervisor 재기동을 시작합니다",
        }

    @app.get("/api/logs/{name}")
    def get_logs(name: str, n: int = 100, type: str = "out"):
        if "/" in name or "\\" in name or ".." in name:
            raise HTTPException(400, "유효하지 않은 이름")
        suffix = "error" if type == "error" else "out"
        log_file = log_dir / f"{name}-{suffix}.log"
        if not log_file.resolve().is_relative_to(log_dir.resolve()):
            raise HTTPException(400, "유효하지 않은 경로")
        if not log_file.exists():
            return {"lines": [], "file": str(log_file)}
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines()
            return {"lines": all_lines[-n:], "file": str(log_file)}
        except OSError:
            return {"lines": [], "file": str(log_file)}

    # --- Static UI ---

    @app.get("/", response_class=HTMLResponse)
    def root():
        html_path = Path(__file__).parent / "static" / "index.html"
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>supervisor dashboard</h1><p>index.html not found</p>")

    return app
