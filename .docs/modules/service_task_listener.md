# service/task_listener.py

> 경로: `seosoyoung/mcp/soul/service/task_listener.py`

## 개요

Task Listener - SSE 리스너 관리

SSE 연결을 통한 이벤트 브로드캐스트를 담당합니다.

## 클래스

### `TaskListenerManager`
- 위치: 줄 16
- 설명: SSE 리스너 관리자

태스크별 리스너 큐를 관리하고 이벤트를 브로드캐스트합니다.

#### 메서드

- `__init__(self, tasks)` (줄 23): Args:
- `async add_listener(self, client_id, request_id, queue)` (줄 30): SSE 리스너 추가
- `async remove_listener(self, client_id, request_id, queue)` (줄 51): SSE 리스너 제거
- `async broadcast(self, client_id, request_id, event)` (줄 66): 모든 리스너에게 이벤트 브로드캐스트

## 내부 의존성

- `seosoyoung.mcp.soul.service.task_models.Task`
