# slack/helpers.py

> 경로: `seosoyoung/slackbot/slack/helpers.py`

## 개요

Slack 메시지 유틸리티

파일 업로드, 긴 메시지 분할 전송, DM 채널 resolve 등의 헬퍼 함수들입니다.

## 함수

### `resolve_operator_dm(client, operator_user_id)`
- 위치: 줄 14
- 설명: 운영자 DM 채널 ID를 획득하고 캐싱한다.

Slack conversations.open API로 운영자와의 IM 채널을 열고,
채널 ID를 모듈 레벨에서 캐싱하여 이후 호출에서 재사용한다.

Args:
    client: Slack WebClient (동기)
    operator_user_id: 운영자의 Slack user ID

Returns:
    DM 채널 ID

### `upload_file_to_slack(client, channel, thread_ts, file_path)`
- 위치: 줄 34
- 설명: 파일을 슬랙에 첨부

Args:
    client: Slack client
    channel: 채널 ID
    thread_ts: 스레드 타임스탬프
    file_path: 첨부할 파일 경로

Returns:
    (success, message): 성공 여부와 메시지

### `send_long_message(say, text, thread_ts, max_length)`
- 위치: 줄 69
- 설명: 긴 메시지를 분할해서 전송 (thread_ts가 None이면 채널에 응답)
