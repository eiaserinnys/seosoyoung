# presentation/activity_board.py

> 경로: `seosoyoung/slackbot/presentation/activity_board.py`

## 개요

ActivityBoard: 플레이스홀더 B 항목 관리

클린 모드에서 thinking/tool/compact 이벤트를 단일 슬랙 메시지의
갱신으로 처리하여 알림 과다 문제를 해결합니다.

## 클래스

### `ActivityItem`
- 위치: 줄 19

### `ActivityBoard`
- 위치: 줄 24
- 설명: 플레이스홀더 B의 항목 리스트를 관리하고 슬랙 메시지를 갱신

#### 메서드

- `__init__(self, client, channel, msg_ts)` (줄 27): 
- `msg_ts(self)` (줄 35): 
- `add(self, item_id, content)` (줄 38): 항목 추가 후 B 메시지 갱신
- `update(self, item_id, content)` (줄 43): 항목 내용 교체 후 B 메시지 갱신. item_id가 없으면 sync를 건너뜀.
- `remove(self, item_id)` (줄 52): 항목 제거 후 B 메시지 갱신
- `schedule_remove(self, item_id, delay)` (줄 58): 지정 시간 후 항목 제거를 예약
- `cancel_all_pending(self)` (줄 75): 모든 대기 중인 제거 태스크를 취소 (cleanup 시 호출)
- `_render(self)` (줄 82): 모든 항목을 하나의 텍스트로 합성
- `_sync(self)` (줄 88): B 메시지를 현재 상태로 갱신

## 내부 의존성

- `seosoyoung.slackbot.slack.formatting.update_message`
