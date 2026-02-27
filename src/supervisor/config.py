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
    soulstream_runtime = root / "soulstream_runtime"
    return {
        "root": root,
        "runtime": runtime,
        "workspace": workspace,
        "venv_python": runtime / "venv" / "Scripts" / "python.exe",
        "mcp_venv_python": runtime / "mcp_venv" / "Scripts" / "python.exe",
        "logs": runtime / "logs",
        "eb_lore": workspace / ".projects" / "eb_lore",
        "eb_narrative": workspace / ".projects" / "eb_narrative",
        "soulstream": workspace / ".projects" / "soulstream",
        "soulstream_runtime": soulstream_runtime,
        "soulstream_venv_python": soulstream_runtime / "venv" / "Scripts" / "python.exe",
        "soulstream_logs": soulstream_runtime / "logs",
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


def _resolve_mcp_servers_dir() -> str:
    """MCP 서버들의 작업 디렉토리를 해석한다. 없으면 생성."""
    raw = os.environ.get("MCP_SERVERS_DIR", os.path.expanduser("~/.mcp-servers"))
    resolved = str(Path(raw).resolve())
    Path(resolved).mkdir(parents=True, exist_ok=True)
    return resolved


def _mcp_outline_available(python: str) -> bool:
    """mcp_venv에 mcp-outline 패키지가 설치되어 있는지 확인."""
    import subprocess
    try:
        subprocess.run(
            [python, "-c", "import mcp_outline"],
            capture_output=True, timeout=5,
        ).check_returncode()
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def build_process_configs() -> list[ProcessConfig]:
    """봇 + MCP 프로세스 설정 생성.

    필수 프로세스(bot) 실패 시 예외 전파, 선택적 MCP 서버는
    FileNotFoundError 시 건너뛰고 로그만 남긴다.
    """
    import logging

    logger = logging.getLogger("supervisor")
    paths = _resolve_paths()
    mcp_servers_dir = _resolve_mcp_servers_dir()

    configs: list[ProcessConfig] = []

    # --- 필수: bot ---
    configs.append(ProcessConfig(
        name="bot",
        command=str(paths["venv_python"]),
        args=["-X", "utf8", "-m", "seosoyoung.slackbot"],
        cwd=str(paths["workspace"].resolve()),
        restart_policy=RestartPolicy(
            use_exit_codes=True,
            auto_restart=True,
        ),
        log_dir=str(paths["logs"]),
        shutdown_url="http://127.0.0.1:3106/shutdown",
    ))

    # --- 필수: mcp-seosoyoung ---
    configs.append(ProcessConfig(
        name="mcp-seosoyoung",
        command=str(paths["mcp_venv_python"]),
        args=["-X", "utf8", "-m", "seosoyoung.mcp", "--transport=sse", "--port=3104"],
        cwd=str(paths["workspace"].resolve()),
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
        port=3104,
    ))

    # --- 선택적: mcp-eb-lore ---
    # eb_lore 리포의 lore_mcp 패키지가 존재할 때만 등록
    eb_lore_mcp_pkg = paths["eb_lore"] / "lore_mcp"
    if eb_lore_mcp_pkg.is_dir():
        configs.append(ProcessConfig(
            name="mcp-eb-lore",
            command=str(paths["mcp_venv_python"]),
            args=["-X", "utf8", "-m", "lore_mcp", "--transport=sse", "--port=3108"],
            cwd=str(paths["workspace"].resolve()),
            restart_policy=RestartPolicy(
                use_exit_codes=False,
                auto_restart=True,
                restart_delay=3.0,
            ),
            log_dir=str(paths["logs"]),
            port=3108,
        ))
    else:
        logger.info("mcp-eb-lore 설정 건너뜀: lore_mcp 패키지 없음 (%s)", eb_lore_mcp_pkg)

    # --- 필수: seosoyoung-soul ---
    # Claude Code 실행 서비스 (FastAPI + uvicorn)
    # venv_python으로 실행 - seosoyoung 패키지 의존
    configs.append(ProcessConfig(
        name="seosoyoung-soul",
        command=str(paths["venv_python"]),
        args=[
            "-X", "utf8", "-m", "uvicorn",
            "seosoyoung.soul.main:app",
            "--host", "127.0.0.1",
            "--port", "3105",
        ],
        cwd=str(paths["workspace"].resolve()),
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=3.0,
        ),
        log_dir=str(paths["logs"]),
        port=3105,
        shutdown_url="http://127.0.0.1:3105/shutdown",
    ))

    # --- 필수: rescue-bot (긴급 복구용 경량 슬랙 봇) ---
    # 메인 봇과 독립된 별도 Slack App 사용 (SocketMode, 포트 불필요)
    configs.append(ProcessConfig(
        name="rescue-bot",
        command=str(paths["venv_python"]),
        args=["-X", "utf8", "-m", "seosoyoung.rescue.main"],
        cwd=str(paths["workspace"].resolve()),
        restart_policy=RestartPolicy(
            use_exit_codes=False,
            auto_restart=True,
            restart_delay=5.0,
        ),
        log_dir=str(paths["logs"]),
        shutdown_url="http://127.0.0.1:3107/shutdown",
    ))

    # --- 선택적: mcp-outline (mcp_venv에서 실행) ---
    mcp_venv_py = str(paths["mcp_venv_python"])
    if _mcp_outline_available(mcp_venv_py):
        configs.append(ProcessConfig(
            name="mcp-outline",
            command=mcp_venv_py,
            args=["-X", "utf8", "-m", "mcp_outline"],
            cwd=mcp_servers_dir,
            restart_policy=RestartPolicy(
                use_exit_codes=False,
                auto_restart=True,
                restart_delay=3.0,
            ),
            log_dir=str(paths["logs"]),
            port=3103,
        ))
    else:
        logger.warning("mcp-outline 설정 건너뜀: mcp_venv에 mcp-outline 미설치")

    # --- 선택적: node 기반 MCP 서버들 ---
    try:
        node = _find_node()
        supergateway = _find_supergateway()

        configs.append(ProcessConfig(
            name="mcp-slack",
            command=node,
            args=[
                supergateway,
                "--stdio", "npx -y slack-mcp-server@latest",
                "--port", "3101",
                "--logLevel", "info",
            ],
            cwd=str(paths["root"].resolve()),
            restart_policy=RestartPolicy(
                use_exit_codes=False,
                auto_restart=True,
                restart_delay=3.0,
            ),
            log_dir=str(paths["logs"]),
            port=3101,
        ))

        configs.append(ProcessConfig(
            name="mcp-trello",
            command=node,
            args=[
                supergateway,
                "--stdio", "npx -y @delorenj/mcp-server-trello",
                "--port", "3102",
                "--logLevel", "info",
            ],
            cwd=mcp_servers_dir,
            restart_policy=RestartPolicy(
                use_exit_codes=False,
                auto_restart=True,
                restart_delay=3.0,
            ),
            log_dir=str(paths["logs"]),
            port=3102,
        ))
    except FileNotFoundError as e:
        logger.warning("node 기반 MCP 서버 설정 건너뜀: %s", e)

    # --- 선택적: soulstream-server (port 4105) ---
    # soulstream 독립 soul-server (soulstream_runtime venv 사용)
    # soul_server 모듈은 soulstream_runtime/venv에 editable install 되어 있어야 함:
    #   pip install -e .projects/soulstream/soul-server --no-deps
    # cwd = soulstream_runtime → load_dotenv()가 soulstream_runtime/.env를 읽음
    # WORKSPACE_DIR = slackbot_workspace → Claude Code 세션의 작업 디렉토리
    soulstream_venv = paths["soulstream_venv_python"]
    soulstream_server_dir = paths["soulstream"] / "soul-server"
    if soulstream_venv.is_file() and soulstream_server_dir.is_dir():
        configs.append(ProcessConfig(
            name="soulstream-server",
            command=str(soulstream_venv),
            args=[
                "-X", "utf8", "-m", "uvicorn",
                "soul_server.main:app",
                "--host", "127.0.0.1",
                "--port", "4105",
            ],
            cwd=str(paths["soulstream_runtime"].resolve()),
            restart_policy=RestartPolicy(
                use_exit_codes=False,
                auto_restart=True,
                restart_delay=3.0,
            ),
            log_dir=str(paths["soulstream_logs"]),
            port=4105,
            shutdown_url="http://127.0.0.1:4105/shutdown",
        ))
    else:
        logger.info(
            "soulstream-server 설정 건너뜀: venv 또는 소스 없음 (%s)",
            soulstream_server_dir,
        )

    # --- 선택적: soulstream-dashboard (TypeScript, port 4109) ---
    soulstream_dashboard_dir = paths["soulstream"] / "soul-dashboard"
    soulstream_tsx = soulstream_dashboard_dir / "node_modules" / "tsx" / "dist" / "cli.mjs"
    soulstream_dashboard_entry = soulstream_dashboard_dir / "server" / "index.ts"

    if soulstream_tsx.is_file() and soulstream_dashboard_entry.is_file():
        try:
            node = _find_node()
            configs.append(ProcessConfig(
                name="soulstream-dashboard",
                command=node,
                args=[str(soulstream_tsx), str(soulstream_dashboard_entry)],
                cwd=str(paths["soulstream_runtime"].resolve()),
                restart_policy=RestartPolicy(
                    use_exit_codes=False,
                    auto_restart=True,
                    restart_delay=3.0,
                ),
                log_dir=str(paths["soulstream_logs"]),
                port=4109,
            ))
        except FileNotFoundError:
            logger.warning("soulstream-dashboard 설정 건너뜀: node를 찾을 수 없음")
    else:
        logger.info(
            "soulstream-dashboard 설정 건너뜀: tsx 또는 서버 엔트리 없음 (%s)",
            soulstream_dashboard_dir,
        )

    # --- 선택적: soul-dashboard (TypeScript, port 3109) ---
    # Soul 실행 내역을 실시간 모니터링하는 대시보드 서버
    dashboard_dir = (
        paths["workspace"] / ".projects" / "seosoyoung"
        / "src" / "soul-dashboard"
    )
    tsx_cli = dashboard_dir / "node_modules" / "tsx" / "dist" / "cli.mjs"
    dashboard_entry = dashboard_dir / "server" / "index.ts"

    if tsx_cli.is_file() and dashboard_entry.is_file():
        try:
            node = _find_node()
            configs.append(ProcessConfig(
                name="soul-dashboard",
                command=node,
                args=[str(tsx_cli), str(dashboard_entry)],
                cwd=str(paths["workspace"].resolve()),
                restart_policy=RestartPolicy(
                    use_exit_codes=False,
                    auto_restart=True,
                    restart_delay=3.0,
                ),
                log_dir=str(paths["logs"]),
                port=3109,
            ))
        except FileNotFoundError:
            logger.warning("soul-dashboard 설정 건너뜀: node를 찾을 수 없음")
    else:
        logger.info(
            "soul-dashboard 설정 건너뜀: tsx 또는 서버 엔트리 없음 (%s)",
            dashboard_dir,
        )

    return configs
