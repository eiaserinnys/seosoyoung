"""supervisor 설정 - 프로세스 정의 및 경로"""

from __future__ import annotations

import os
from pathlib import Path

from .models import ProcessConfig, RestartPolicy


def _resolve_paths() -> dict[str, Path]:
    """경로 해석. 환경변수 SOYOUNG_ROOT로 오버라이드 가능."""
    root = Path(os.environ.get("SOYOUNG_ROOT", "D:/soyoung_root"))
    runtime = root / "seosoyoung_runtime"
    workspace = root / "slackbot_workspace"
    return {
        "root": root,
        "runtime": runtime,
        "workspace": workspace,
        "venv_python": runtime / "venv" / "Scripts" / "python.exe",
        "logs": runtime / "logs",
    }


def build_process_configs() -> list[ProcessConfig]:
    """봇 + MCP 프로세스 설정 생성"""
    paths = _resolve_paths()

    bot = ProcessConfig(
        name="bot",
        command=str(paths["venv_python"]),
        args=["-m", "seosoyoung.main"],
        cwd=str(paths["workspace"]),
        env={
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(paths["runtime"] / "src"),
        },
        restart_policy=RestartPolicy(
            use_exit_codes=True,
            auto_restart=True,
        ),
        log_dir=str(paths["logs"]),
    )

    mcp = ProcessConfig(
        name="mcp",
        command=str(paths["venv_python"]),
        args=["-m", "seosoyoung.mcp"],
        cwd=str(paths["runtime"]),
        env={
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(paths["workspace"] / "seosoyoung" / "src"),
        },
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
    )

    return [bot, mcp]
