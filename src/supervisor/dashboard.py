"""대시보드 - FastAPI 기반 웹 UI + REST API"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from .deployer import Deployer
    from .git_poller import GitPoller
    from .process_manager import ProcessManager

_VALID_ACTIONS = {"start", "stop", "restart"}


def create_app(
    *,
    process_manager: ProcessManager,
    deployer: Deployer,
    git_poller: GitPoller,
    log_dir: Path,
) -> FastAPI:
    """FastAPI 앱을 생성하고 라우트를 등록한다."""

    app = FastAPI(title="supervisor dashboard", docs_url=None, redoc_url=None)

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
