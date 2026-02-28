# rescue/slack_utils.py

> 경로: `seosoyoung/rescue/slack_utils.py`

## 개요

rescue-bot용 슬랙 메시지 포맷팅 헬퍼

slackbot.slack.formatting에서 이관된 경량 유틸리티.

## 함수

### `build_section_blocks(text)`
- 위치: 줄 9
- 설명: mrkdwn section block 리스트 생성

### `update_message(client, channel, ts, text)`
- 위치: 줄 17
- 설명: 슬랙 메시지를 업데이트합니다.

blocks를 생략하면 text를 mrkdwn section block으로 자동 감싸서 전달합니다.
