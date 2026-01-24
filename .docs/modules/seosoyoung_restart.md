# seosoyoung/restart.py

> 경로: `seosoyoung/restart.py`

## 개요

재시작 관리

재시작 대기 상태 및 확인 프로세스를 관리합니다.

## 클래스

### `RestartType` (Enum)
- 위치: 줄 15
- 설명: 재시작 유형

### `RestartRequest`
- 위치: 줄 22
- 설명: 재시작 요청 정보

### `RestartManager`
- 위치: 줄 30
- 설명: 재시작 관리자

재시작 요청을 받으면 활성 세션을 확인하고,
필요시 대기 모드로 전환합니다.

#### 메서드

- `__init__(self, get_running_count, on_restart)` (줄 37): Args:
- `is_pending(self)` (줄 55): 재시작 대기 중인지 확인
- `pending_request(self)` (줄 61): 대기 중인 재시작 요청 반환
- `request_restart(self, request)` (줄 66): 재시작 요청 (대기 모드 진입)
- `cancel_restart(self)` (줄 84): 재시작 대기 취소
- `check_and_restart_if_ready(self)` (줄 98): 실행 중인 세션이 없으면 재시작 실행
- `force_restart(self, restart_type)` (줄 120): 즉시 재시작 (대기 없이)
