"""supervisor 설정 - 프로세스 정의 및 경로"""

from __future__ import annotations

import os
import shutil
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
        "mcp_venv_python": runtime / "mcp_venv" / "Scripts" / "python.exe",
        "logs": runtime / "logs",
    }


def _find_node() -> str:
    """node 실행 파일 경로를 찾는다."""
    node = shutil.which("node")
    if node:
        return node
    raise FileNotFoundError("node를 찾을 수 없습니다. PATH에 포함되어 있는지 확인하세요.")


def _find_supergateway() -> str:
    """supergateway index.js 경로를 찾는다."""
    path = os.environ.get("SUPERGATEWAY_PATH")
    if path and Path(path).exists():
        return str(Path(path))
    npm_prefix = Path(os.environ.get(
        "NPM_GLOBAL_PREFIX",
        os.path.expanduser("~/AppData/Roaming/npm"),
    ))
    candidate = npm_prefix / "node_modules" / "supergateway" / "dist" / "index.js"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(
        "supergateway를 찾을 수 없습니다. "
        "SUPERGATEWAY_PATH 환경변수를 설정하거나 npm install -g supergateway를 실행하세요."
    )


def _find_mcp_outline_exe() -> str:
    """mcp-outline 실행 파일 경로를 찾는다."""
    path = os.environ.get("MCP_OUTLINE_EXE")
    if path and Path(path).exists():
        return path
    exe = shutil.which("mcp-outline")
    if exe:
        return exe
    raise FileNotFoundError(
        "mcp-outline을 찾을 수 없습니다. "
        "MCP_OUTLINE_EXE 환경변수를 설정하거나 pip install mcp-outline을 실행하세요."
    )


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

    mcp_seosoyoung = ProcessConfig(
        name="mcp-seosoyoung",
        command=str(paths["mcp_venv_python"]),
        args=["-m", "seosoyoung.mcp", "--transport=sse", "--port=3104"],
        cwd=str(paths["root"]),
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

    mcp_outline = ProcessConfig(
        name="mcp-outline",
        command=_find_mcp_outline_exe(),
        args=[],
        cwd=os.environ.get("MCP_SERVERS_DIR", os.path.expanduser("~/.mcp-servers")),
        env={
            "MCP_TRANSPORT": "sse",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": "3103",
        },
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
    )

    node = _find_node()
    supergateway = _find_supergateway()

    mcp_slack = ProcessConfig(
        name="mcp-slack",
        command=node,
        args=[
            supergateway,
            "--stdio", "npx -y slack-mcp-server@latest",
            "--port", "3101",
            "--logLevel", "info",
        ],
        cwd=str(paths["root"]),
        env={},
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
    )

    mcp_trello = ProcessConfig(
        name="mcp-trello",
        command=node,
        args=[
            supergateway,
            "--stdio", "npx -y @delorenj/mcp-server-trello",
            "--port", "3102",
            "--logLevel", "info",
        ],
        cwd=os.environ.get("MCP_SERVERS_DIR", os.path.expanduser("~/.mcp-servers")),
        env={},
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
    )

    return [bot, mcp_seosoyoung, mcp_outline, mcp_slack, mcp_trello]
