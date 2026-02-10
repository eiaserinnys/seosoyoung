"""seosoyoung MCP 서버 정의"""

from fastmcp import FastMCP

from seosoyoung.mcp.tools.attach import attach_file, get_slack_context

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
