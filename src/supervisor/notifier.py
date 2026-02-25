"""Notifier - 배포 Slack 웹훅 알림"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger("supervisor")

_MAX_COMMITS_DISPLAY = 10


def load_webhook_url(config_path: Path) -> str | None:
    """watchdog_config.json에서 Slack 웹훅 URL을 읽는다.

    파일이 없거나 키가 없으면 None을 반환한다.
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        url = data.get("slackWebhookUrl", "")
        return url if url else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def get_pending_commits(repo_path: Path) -> list[str]:
    """HEAD..origin/main 범위의 pending 커밋 목록을 가져온다.

    각 항목은 ``git log --oneline`` 형식의 문자열이다.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--no-decorate", "HEAD..origin/main"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("git log 실패 (%s): %s", repo_path, result.stderr.strip())
            return []
        return [line for line in result.stdout.strip().split("\n") if line.strip()]
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("커밋 목록 조회 실패 (%s): %s", repo_path, exc)
        return []


def _format_commit_section(title: str, commits: list[str]) -> list[str]:
    """커밋 목록을 Slack 메시지 섹션으로 포맷한다."""
    if not commits:
        return []
    lines: list[str] = ["", f"*{title}*"]
    display = commits[:_MAX_COMMITS_DISPLAY]
    for entry in display:
        entry = entry.strip()
        if not entry:
            continue
        hash_part = entry[:7]
        msg_part = entry[8:] if len(entry) > 8 else ""
        lines.append(f"`{hash_part}` {msg_part}")
    overflow = len(commits) - _MAX_COMMITS_DISPLAY
    if overflow > 0:
        lines.append(f"... 외 {overflow}건")
    return lines


def format_deploy_start_message(
    runtime_commits: list[str],
    seosoyoung_commits: list[str],
) -> str:
    """배포 시작 메시지를 생성한다."""
    lines = [":arrows_counterclockwise: *서소영 업데이트합니다...*"]
    lines.extend(_format_commit_section("runtime", runtime_commits))
    lines.extend(_format_commit_section("seosoyoung", seosoyoung_commits))
    return "\n".join(lines)


def format_deploy_success_message() -> str:
    """배포 성공 메시지를 생성한다."""
    return ":white_check_mark: *업데이트 완료*"


def format_deploy_failure_message(error: str | None = None) -> str:
    """배포 실패 메시지를 생성한다."""
    msg = ":x: *업데이트 실패*"
    if error:
        msg += f"\n```{error}```"
    return msg


def send_webhook(url: str, message: str) -> None:
    """Slack 웹훅으로 메시지를 전송한다."""
    try:
        body = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info("Slack 웹훅 전송 완료")
    except Exception:
        logger.exception("Slack 웹훅 전송 실패")


def _get_default_config_path(paths: dict[str, Path]) -> Path:
    """기본 watchdog_config.json 경로를 반환한다."""
    return paths["runtime"] / "data" / "watchdog_config.json"


def notify_deploy_start(
    paths: dict[str, Path],
    config_path: Path | None = None,
) -> None:
    """배포 시작 알림을 전송한다."""
    if config_path is None:
        config_path = _get_default_config_path(paths)
    url = load_webhook_url(config_path)
    if not url:
        return

    runtime_commits = get_pending_commits(paths["runtime"])
    dev_seosoyoung = paths["workspace"] / "seosoyoung"
    seosoyoung_commits = (
        get_pending_commits(dev_seosoyoung)
        if dev_seosoyoung.exists()
        else []
    )

    message = format_deploy_start_message(runtime_commits, seosoyoung_commits)
    send_webhook(url, message)


def notify_deploy_success(config_path: Path | None = None) -> None:
    """배포 성공 알림을 전송한다."""
    if config_path is None:
        return
    url = load_webhook_url(config_path)
    if not url:
        return
    send_webhook(url, format_deploy_success_message())


def notify_deploy_failure(
    config_path: Path | None = None,
    error: str | None = None,
) -> None:
    """배포 실패 알림을 전송한다."""
    if config_path is None:
        return
    url = load_webhook_url(config_path)
    if not url:
        return
    send_webhook(url, format_deploy_failure_message(error))


def format_change_detected_message(
    runtime_commits: list[str],
    seosoyoung_commits: list[str],
) -> str:
    """변경점 감지 메시지를 생성한다."""
    lines = [":mag: *변경점이 발견됐습니다*"]
    lines.extend(_format_commit_section("runtime", runtime_commits))
    lines.extend(_format_commit_section("seosoyoung", seosoyoung_commits))
    return "\n".join(lines)


def format_waiting_sessions_message() -> str:
    """세션 대기 메시지를 생성한다."""
    return ":hourglass_flowing_sand: *재시작을 대기합니다...*"


def notify_change_detected(
    paths: dict[str, Path],
    config_path: Path | None = None,
) -> None:
    """변경점 감지 알림을 전송한다."""
    if config_path is None:
        config_path = _get_default_config_path(paths)
    url = load_webhook_url(config_path)
    if not url:
        return

    runtime_commits = get_pending_commits(paths["runtime"])
    dev_seosoyoung = paths["workspace"] / "seosoyoung"
    seosoyoung_commits = (
        get_pending_commits(dev_seosoyoung)
        if dev_seosoyoung.exists()
        else []
    )

    message = format_change_detected_message(runtime_commits, seosoyoung_commits)
    send_webhook(url, message)


def notify_waiting_sessions(
    config_path: Path | None = None,
) -> None:
    """세션 대기 알림을 전송한다."""
    if config_path is None:
        return
    url = load_webhook_url(config_path)
    if not url:
        return
    send_webhook(url, format_waiting_sessions_message())
