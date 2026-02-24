# slack/helpers.py

> 경로: `seosoyoung/slackbot/slack/helpers.py`

## 개요

Slack 메시지 유틸리티

파일 업로드, 긴 메시지 분할 전송 등의 헬퍼 함수들입니다.

## 함수

### `upload_file_to_slack(client, channel, thread_ts, file_path)`
- 위치: 줄 12
- 설명: 파일을 슬랙에 첨부

Args:
    client: Slack client
    channel: 채널 ID
    thread_ts: 스레드 타임스탬프
    file_path: 첨부할 파일 경로

Returns:
    (success, message): 성공 여부와 메시지

### `send_long_message(say, text, thread_ts, max_length)`
- 위치: 줄 47
- 설명: 긴 메시지를 분할해서 전송 (thread_ts가 None이면 채널에 응답)
