"""스레드 내 파일 다운로드 MCP 도구"""

import logging
from typing import Any

from slack_sdk import WebClient

from seosoyoung.mcp.config import SLACK_BOT_TOKEN
from seosoyoung.slackbot.slack.file_handler import download_file

logger = logging.getLogger(__name__)


def _get_slack_client() -> WebClient:
    """Slack WebClient 인스턴스 반환"""
    return WebClient(token=SLACK_BOT_TOKEN)


async def download_thread_files(channel: str, thread_ts: str) -> dict[str, Any]:
    """스레드 내 모든 메시지의 첨부 파일을 다운로드

    Slack conversations.replies API로 스레드 메시지를 조회하고,
    파일이 있는 메시지에서 파일을 다운로드합니다.
    기존 slack/file_handler.py의 download_file()을 재활용합니다.

    Args:
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프

    Returns:
        {
            success: bool,
            files: [{ local_path, original_name, size, file_type, message_ts }],
            message: str
        }
    """
    try:
        client = _get_slack_client()
        response = client.conversations_replies(
            channel=channel,
            ts=thread_ts,
        )
    except Exception as e:
        logger.error(f"스레드 메시지 조회 실패: channel={channel}, ts={thread_ts}, error={e}")
        return {
            "success": False,
            "files": [],
            "message": f"스레드 메시지 조회 실패: {e}",
        }

    messages = response.get("messages", [])

    # 파일이 있는 메시지에서 파일 정보 수집
    file_entries: list[tuple[str, dict]] = []  # (message_ts, file_info)
    for msg in messages:
        msg_ts = msg.get("ts", "")
        for file_info in msg.get("files", []):
            file_entries.append((msg_ts, file_info))

    if not file_entries:
        return {
            "success": True,
            "files": [],
            "message": "스레드에 파일 없음",
        }

    # 파일 다운로드
    downloaded = []
    for msg_ts, file_info in file_entries:
        result = await download_file(file_info, thread_ts)
        if result:
            downloaded.append({
                "local_path": result["local_path"],
                "original_name": result["original_name"],
                "size": result["size"],
                "file_type": result["file_type"],
                "message_ts": msg_ts,
            })

    return {
        "success": True,
        "files": downloaded,
        "message": f"{len(downloaded)}개 파일 다운로드 완료",
    }
