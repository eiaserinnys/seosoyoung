# handlers/channel_collector.py

> 경로: `seosoyoung/handlers/channel_collector.py`

## 개요

채널 메시지 수집기

관찰 대상 채널의 메시지를 ChannelStore 버퍼에 저장합니다.

## 클래스

### `ChannelMessageCollector`
- 위치: 줄 13
- 설명: 관찰 대상 채널의 메시지를 수집하여 버퍼에 저장

#### 메서드

- `__init__(self, store, target_channels)` (줄 27): 
- `collect(self, event)` (줄 31): 이벤트에서 메시지를 추출하여 버퍼에 저장.
- `collect_reaction(self, event, action)` (줄 85): 리액션 이벤트에서 reactions 필드를 갱신합니다.

## 내부 의존성

- `seosoyoung.memory.channel_store.ChannelStore`
