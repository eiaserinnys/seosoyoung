# handlers/mention_tracker.py

> 경로: `seosoyoung/slackbot/handlers/mention_tracker.py`

## 개요

멘션으로 처리 중인 스레드를 추적

채널 관찰자(channel observer)가 멘션 핸들러와 동일한 메시지/스레드를
중복 처리하지 않도록, 멘션으로 이미 처리 중인 스레드의 thread_ts를
인메모리 세트로 관리합니다.

## 클래스

### `MentionTracker`
- 위치: 줄 13
- 설명: 멘션으로 처리 중인 스레드를 추적

#### 메서드

- `__init__(self)` (줄 16): 
- `mark(self, thread_ts)` (줄 19): 멘션 핸들러가 처리한 스레드를 등록
- `is_handled(self, thread_ts)` (줄 25): 해당 스레드가 멘션으로 처리 중인지 확인
- `unmark(self, thread_ts)` (줄 29): 스레드 추적 해제
- `handled_count(self)` (줄 35): 현재 추적 중인 스레드 수
