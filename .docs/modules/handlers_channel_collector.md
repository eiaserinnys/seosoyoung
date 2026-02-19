# handlers/channel_collector.py

> 경로: `seosoyoung/handlers/channel_collector.py`

## 개요

채널 메시지 수집기

관찰 대상 채널의 메시지를 ChannelStore 버퍼에 저장합니다.

## 클래스

### `ChannelMessageCollector`
- 위치: 줄 19
- 설명: 관찰 대상 채널의 메시지를 수집하여 버퍼에 저장

#### 메서드

- `__init__(self, store, target_channels, mention_tracker, bot_user_id)` (줄 33): 
- `bot_user_id(self)` (줄 46): 봇 사용자 ID (런타임에 설정될 수 있으므로 프로퍼티로 제공)
- `_detect_and_mark_mention(self, text, ts, thread_ts)` (줄 57): 메시지 텍스트에 봇 멘션이 포함되어 있으면 mention_tracker에 마킹.
- `collect(self, event)` (줄 83): 이벤트에서 메시지를 추출하여 버퍼에 저장.
- `collect_reaction(self, event, action)` (줄 158): 리액션 이벤트에서 reactions 필드를 갱신합니다.

## 내부 의존성

- `seosoyoung.memory.channel_store.ChannelStore`
