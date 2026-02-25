# slack/message_formatter.py

> 경로: `seosoyoung/slackbot/slack/message_formatter.py`

## 개요

슬랙 메시지 → 프롬프트 주입 포맷터

모든 슬랙 메시지를 Claude 프롬프트에 주입할 때 사용하는 통일된 포맷터입니다.
채널:ts 메타데이터, Block Kit 리치 텍스트, 첨부 파일, unfurl, 리액션 등을 포함합니다.

## 함수

### `format_slack_message(msg, channel, include_meta)`
- 위치: 줄 8
- 설명: 슬랙 메시지를 프롬프트 주입용 텍스트로 포맷합니다.

Args:
    msg: 슬랙 메시지 dict (conversations.history 등에서 반환되는 형태)
    channel: 슬랙 채널 ID
    include_meta: True면 [channel:ts] 메타데이터 프리픽스 부착

Returns:
    포맷된 문자열

### `_format_blocks(blocks)`
- 위치: 줄 81
- 설명: Block Kit rich_text 요소를 텍스트로 변환
