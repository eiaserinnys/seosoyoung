# slack/formatting.py

> 경로: `seosoyoung/slackbot/slack/formatting.py`

## 개요

슬랙 메시지 포맷팅 헬퍼

chat_update(channel, ts, text, blocks=[section]) 패턴을 캡슐화합니다.

## 함수

### `build_section_blocks(text)`
- 위치: 줄 9
- 설명: mrkdwn section block 리스트 생성

### `update_message(client, channel, ts, text)`
- 위치: 줄 17
- 설명: 슬랙 메시지를 업데이트합니다.

blocks를 생략하면 text를 mrkdwn section block으로 자동 감싸서 전달합니다.

Args:
    client: Slack WebClient
    channel: 채널 ID
    ts: 메시지 타임스탬프
    text: 메시지 텍스트
    blocks: 커스텀 blocks (생략 시 text로 자동 생성)
