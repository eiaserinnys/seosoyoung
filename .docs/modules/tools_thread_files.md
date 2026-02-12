# tools/thread_files.py

> 경로: `seosoyoung/mcp/tools/thread_files.py`

## 개요

스레드 내 파일 다운로드 MCP 도구

## 함수

### `_get_slack_client()`
- 위치: 줄 14
- 설명: Slack WebClient 인스턴스 반환

### `async download_thread_files(channel, thread_ts)`
- 위치: 줄 19
- 설명: 스레드 내 모든 메시지의 첨부 파일을 다운로드

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

## 내부 의존성

- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
- `seosoyoung.slack.file_handler.download_file`
