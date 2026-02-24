# claude/reaction_manager.py

> 경로: `seosoyoung/claude/reaction_manager.py`

## 개요

슬랙 리액션 관리

트렐로 모드 및 멘션 모드에서 메시지에 이모지 리액션을 추가/제거하는 기능을 제공합니다.

## 함수

### `add_reaction(client, channel, ts, emoji)`
- 위치: 줄 33
- 설명: 슬랙 메시지에 이모지 리액션 추가

Args:
    client: Slack client
    channel: 채널 ID
    ts: 메시지 타임스탬프
    emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

Returns:
    성공 여부

### `remove_reaction(client, channel, ts, emoji)`
- 위치: 줄 53
- 설명: 슬랙 메시지에서 이모지 리액션 제거

Args:
    client: Slack client
    channel: 채널 ID
    ts: 메시지 타임스탬프
    emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

Returns:
    성공 여부

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
