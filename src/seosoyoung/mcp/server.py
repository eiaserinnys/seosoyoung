"""seosoyoung MCP 서버 정의"""

from typing import Optional

from fastmcp import FastMCP

from seosoyoung.mcp.tools.attach import attach_file, get_slack_context
from seosoyoung.mcp.tools.slack_messaging import post_message
from seosoyoung.mcp.tools.thread_files import download_thread_files

mcp = FastMCP("seosoyoung-attach")


@mcp.tool()
def slack_attach_file(file_path: str, channel: str, thread_ts: str) -> dict:
    """슬랙에 파일을 첨부합니다.

    workspace(slackbot_workspace) 내부 파일만 허용됩니다.
    허용 확장자: .md, .txt, .yaml, .yml, .json, .csv, .png, .jpg, .pdf 등
    최대 파일 크기: 20MB

    Args:
        file_path: 첨부할 파일의 절대 경로
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
    """
    return attach_file(file_path, channel, thread_ts)


@mcp.tool()
def slack_get_context() -> dict:
    """현재 슬랙 대화의 채널/스레드 정보를 반환합니다.

    환경변수 SLACK_CHANNEL, SLACK_THREAD_TS에서 읽어 반환합니다.
    attach_file 호출 전에 컨텍스트를 조회할 때 사용합니다.
    """
    return get_slack_context()


@mcp.tool()
def slack_post_message(
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
    file_paths: Optional[str] = None,
) -> dict:
    """봇 권한으로 슬랙 채널에 메시지를 보냅니다.

    텍스트 전송과 파일 첨부를 모두 지원합니다.
    파일 첨부 시 workspace 내부 파일만 허용됩니다.

    Args:
        channel: 슬랙 채널 ID (필수)
        text: 메시지 텍스트 (필수)
        thread_ts: 스레드 타임스탬프 (선택)
        file_paths: 파일 경로, 쉼표 구분 (선택)
    """
    return post_message(channel, text, thread_ts or "", file_paths or "")


@mcp.tool()
async def slack_download_thread_files(channel: str, thread_ts: str) -> dict:
    """스레드 내 모든 메시지의 첨부 파일을 다운로드합니다.

    Slack conversations.replies API로 스레드 메시지를 조회하고,
    파일이 있는 메시지에서 파일을 로컬로 다운로드합니다.

    Args:
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
    """
    return await download_thread_files(channel, thread_ts)
