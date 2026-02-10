# tools/attach.py

> 경로: `seosoyoung/mcp/tools/attach.py`

## 개요

파일 첨부 및 슬랙 컨텍스트 MCP 도구

## 함수

### `_get_slack_client()`
- 위치: 줄 19
- 설명: Slack WebClient 인스턴스 반환

### `get_slack_context()`
- 위치: 줄 24
- 설명: 현재 대화의 채널/스레드 정보를 환경변수에서 읽어 반환

Returns:
    dict: channel, thread_ts 키를 포함하는 딕셔너리

### `attach_file(file_path, channel, thread_ts)`
- 위치: 줄 36
- 설명: 슬랙에 파일을 첨부

Args:
    file_path: 첨부할 파일의 절대 경로
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프

Returns:
    dict: success(bool), message(str) 키를 포함하는 결과 딕셔너리

## 내부 의존성

- `seosoyoung.mcp.config.ALLOWED_EXTENSIONS`
- `seosoyoung.mcp.config.MAX_FILE_SIZE`
- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
- `seosoyoung.mcp.config.WORKSPACE_ROOT`
