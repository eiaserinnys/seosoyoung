# claude/types.py

> 경로: `seosoyoung/slackbot/claude/types.py`

## 개요

claude/ 모듈 내부 Protocol 정의

외부 의존성(TrackedCard, Config 등)을 제거하기 위한 인터페이스 타입입니다.
런타임 체크를 지원하여 duck-typing 호환 객체를 받을 수 있습니다.

## 클래스

### `CardInfo` (Protocol)
- 위치: 줄 11
- 설명: 트렐로 카드 정보 Protocol (TrackedCard 대체)

claude/ 모듈이 필요로 하는 카드 속성만 정의합니다.

#### 메서드

- `card_id(self)` (줄 18): 
- `card_name(self)` (줄 21): 
- `card_url(self)` (줄 24): 
- `list_key(self)` (줄 27): 
- `has_execute(self)` (줄 30): 
- `session_id(self)` (줄 33): 
- `dm_thread_ts(self)` (줄 36): 

### `SlackClient` (Protocol)
- 위치: 줄 40
- 설명: Slack WebClient Protocol

claude/ 모듈이 사용하는 Slack API 메서드만 정의합니다.

#### 메서드

- `chat_postMessage(self)` (줄 46): 
- `chat_update(self)` (줄 47): 
