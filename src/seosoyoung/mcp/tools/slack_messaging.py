"""슬랙 메시지 전송 MCP 도구"""

import logging
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


def _validate_file(file_path: str) -> str | None:
    """파일 검증. 문제가 있으면 에러 메시지 반환, 없으면 None."""
    resolved = Path(file_path).resolve()

    if not resolved.exists():
        return f"파일이 존재하지 않음: {file_path}"

    if not resolved.is_file():
        return f"파일이 아님: {file_path}"

    workspace = Path(WORKSPACE_ROOT).resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return f"workspace 외부 파일은 허용되지 않음: {file_path}"

    ext = resolved.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"허용되지 않는 확장자: {ext}"

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        return f"파일 크기 초과: {size_mb:.1f}MB (최대 20MB)"

    return None


def post_message(
    channel: str,
    text: str,
    thread_ts: str = "",
    file_paths: str = "",
) -> dict:
    """슬랙 채널에 메시지를 전송하고 선택적으로 파일을 첨부

    Args:
        channel: 채널 ID (필수)
        text: 메시지 텍스트 (필수)
        thread_ts: 스레드 ts (선택)
        file_paths: 파일 경로, 쉼표 구분 (선택)

    Returns:
        dict: success(bool), message(str) 키를 포함하는 결과 딕셔너리
    """
    # 파일 경로 파싱 및 검증 (파일이 있으면 먼저 검증)
    files_to_upload: list[Path] = []
    if file_paths.strip():
        for fp in file_paths.split(","):
            fp = fp.strip()
            if not fp:
                continue
            error = _validate_file(fp)
            if error:
                return {"success": False, "message": error}
            files_to_upload.append(Path(fp).resolve())

    try:
        client = _get_slack_client()

        # 텍스트 메시지 전송
        msg_kwargs: dict = {"channel": channel, "text": text}
        if thread_ts:
            msg_kwargs["thread_ts"] = thread_ts

        response = client.chat_postMessage(**msg_kwargs)
        msg_ts = response.get("ts", "")

        # 파일 첨부
        file_errors: list[str] = []
        uploaded_files: list[str] = []
        # 파일은 메시지의 스레드에 첨부 (thread_ts가 있으면 그 스레드, 없으면 방금 보낸 메시지의 ts)
        attach_thread_ts = thread_ts or msg_ts

        for resolved in files_to_upload:
            try:
                client.files_upload_v2(
                    channel=channel,
                    thread_ts=attach_thread_ts,
                    file=str(resolved),
                    filename=resolved.name,
                )
                uploaded_files.append(resolved.name)
                logger.info(f"파일 업로드 성공: {resolved.name}")
            except Exception as e:
                error_msg = f"{resolved.name}: {e}"
                file_errors.append(error_msg)
                logger.error(f"파일 업로드 실패: {error_msg}")

        # 결과 조립
        result: dict = {"success": True, "message": f"메시지 전송 완료 (ts: {msg_ts})"}
        if uploaded_files:
            result["uploaded_files"] = uploaded_files
        if file_errors:
            result["file_errors"] = file_errors
            result["message"] += f" / 파일 업로드 실패: {', '.join(file_errors)}"

        return result

    except Exception as e:
        logger.error(f"메시지 전송 실패: {e}")
        return {"success": False, "message": f"메시지 전송 실패: {e}"}
