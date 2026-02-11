# tools/slack_messaging.py

> 경로: `seosoyoung/mcp/tools/slack_messaging.py`

## 개요

슬랙 메시지 전송 MCP 도구

## 함수

### `_get_slack_client()`
- 위치: 줄 18
- 설명: Slack WebClient 인스턴스 반환

### `_validate_file(file_path)`
- 위치: 줄 23
- 설명: 파일 검증. 문제가 있으면 에러 메시지 반환, 없으면 None.

### `post_message(channel, text, thread_ts, file_paths)`
- 위치: 줄 51
- 설명: 슬랙 채널에 메시지를 전송하고 선택적으로 파일을 첨부

Args:
    channel: 채널 ID (필수)
    text: 메시지 텍스트 (필수)
    thread_ts: 스레드 ts (선택)
    file_paths: 파일 경로, 쉼표 구분 (선택)

Returns:
    dict: success(bool), message(str) 키를 포함하는 결과 딕셔너리

## 내부 의존성

- `seosoyoung.mcp.config.ALLOWED_EXTENSIONS`
- `seosoyoung.mcp.config.MAX_FILE_SIZE`
- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
- `seosoyoung.mcp.config.WORKSPACE_ROOT`
