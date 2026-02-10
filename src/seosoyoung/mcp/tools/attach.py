"""파일 첨부 및 슬랙 컨텍스트 MCP 도구"""

import logging
import os
from pathlib import Path

from slack_sdk import WebClient

from seosoyoung.mcp.config import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    SLACK_BOT_TOKEN,
    WORKSPACE_ROOT,
)

logger = logging.getLogger(__name__)


def _get_slack_client() -> WebClient:
    """Slack WebClient 인스턴스 반환"""
    return WebClient(token=SLACK_BOT_TOKEN)


def get_slack_context() -> dict:
    """현재 대화의 채널/스레드 정보를 환경변수에서 읽어 반환

    Returns:
        dict: channel, thread_ts 키를 포함하는 딕셔너리
    """
    return {
        "channel": os.environ.get("SLACK_CHANNEL", ""),
        "thread_ts": os.environ.get("SLACK_THREAD_TS", ""),
    }


def attach_file(file_path: str, channel: str, thread_ts: str) -> dict:
    """슬랙에 파일을 첨부

    Args:
        file_path: 첨부할 파일의 절대 경로
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프

    Returns:
        dict: success(bool), message(str) 키를 포함하는 결과 딕셔너리
    """
    resolved = Path(file_path).resolve()

    if not resolved.exists():
        return {"success": False, "message": f"파일이 존재하지 않음: {file_path}"}

    if not resolved.is_file():
        return {"success": False, "message": f"파일이 아님: {file_path}"}

    # workspace 내부 파일만 허용
    workspace = Path(WORKSPACE_ROOT).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return {"success": False, "message": f"workspace 외부 파일은 허용되지 않음: {file_path}"}

    # 확장자 검증
    ext = resolved.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {"success": False, "message": f"허용되지 않는 확장자: {ext}"}

    # 파일 크기 검증
    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        return {"success": False, "message": f"파일 크기 초과: {size_mb:.1f}MB (최대 20MB)"}

    # 슬랙 업로드
    try:
        client = _get_slack_client()
        client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file=str(resolved),
            filename=resolved.name,
            initial_comment=f"📎 `{resolved.name}`",
        )
        logger.info(f"파일 첨부 성공: {file_path}")
        return {"success": True, "message": f"첨부 완료: {resolved.name}"}
    except Exception as e:
        logger.error(f"파일 첨부 실패: {file_path} - {e}")
        return {"success": False, "message": f"첨부 실패: {e}"}
