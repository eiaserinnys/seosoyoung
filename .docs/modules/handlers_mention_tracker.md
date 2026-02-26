# handlers/mention_tracker.py

> 경로: `seosoyoung/slackbot/handlers/mention_tracker.py`

## 개요

멘션으로 처리 중인 스레드를 추적

채널 관찰자(channel observer)가 멘션 핸들러와 동일한 메시지/스레드를
중복 처리하지 않도록, 멘션으로 이미 처리 중인 스레드의 thread_ts를
인메모리 딕셔너리로 관리합니다.

TTL 기반 자동 만료를 지원하여, 멘션 처리 완료 후 명시적으로
unmark()를 호출하지 않아도 일정 시간 후 자동으로 해제됩니다.

## 클래스

### `MentionTracker`
- 위치: 줄 20
- 설명: 멘션으로 처리 중인 스레드를 추적 (TTL 기반 자동 만료)

#### 메서드

- `__init__(self, ttl_seconds)` (줄 23): 
- `mark(self, thread_ts)` (줄 27): 멘션 핸들러가 처리한 스레드를 등록
- `is_handled(self, thread_ts)` (줄 34): 해당 스레드가 멘션으로 처리 중인지 확인
- `unmark(self, thread_ts)` (줄 39): 스레드 추적 해제
- `handled_count(self)` (줄 45): 현재 추적 중인 스레드 수
- `_expire(self)` (줄 50): TTL을 초과한 항목을 제거
