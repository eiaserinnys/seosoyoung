# mcp/server.py

> 경로: `seosoyoung/mcp/server.py`

## 개요

seosoyoung MCP 서버 정의

## 함수

### `slack_attach_file(file_path, channel, thread_ts)`
- 위치: 줄 12
- 데코레이터: mcp.tool
- 설명: 슬랙에 파일을 첨부합니다.

workspace(slackbot_workspace) 내부 파일만 허용됩니다.
허용 확장자: .md, .txt, .yaml, .yml, .json, .csv, .png, .jpg, .pdf 등
최대 파일 크기: 20MB

Args:
    file_path: 첨부할 파일의 절대 경로
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프

### `slack_get_context()`
- 위치: 줄 28
- 데코레이터: mcp.tool
- 설명: 현재 슬랙 대화의 채널/스레드 정보를 반환합니다.

환경변수 SLACK_CHANNEL, SLACK_THREAD_TS에서 읽어 반환합니다.
attach_file 호출 전에 컨텍스트를 조회할 때 사용합니다.

### `slack_post_message(channel, text, thread_ts, file_paths)`
- 위치: 줄 38
- 데코레이터: mcp.tool
- 설명: 봇 권한으로 슬랙 채널에 메시지를 보냅니다.

텍스트 전송과 파일 첨부를 모두 지원합니다.
파일 첨부 시 workspace 내부 파일만 허용됩니다.

Args:
    channel: 슬랙 채널 ID (필수)
    text: 메시지 텍스트 (필수)
    thread_ts: 스레드 타임스탬프 (선택)
    file_paths: 파일 경로, 쉼표 구분 (선택)

## 내부 의존성

- `seosoyoung.mcp.tools.attach.attach_file`
- `seosoyoung.mcp.tools.attach.get_slack_context`
- `seosoyoung.mcp.tools.slack_messaging.post_message`
