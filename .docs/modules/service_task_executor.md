# service/task_executor.py

> 경로: `seosoyoung/soul/service/task_executor.py`

## 개요

Task Executor - 백그라운드 태스크 실행 관리

Claude Code 실행을 백그라운드에서 관리합니다.

## 클래스

### `TaskExecutor`
- 위치: 줄 19
- 설명: 백그라운드 태스크 실행 관리자

Claude Code 실행을 백그라운드에서 관리하고,
실행 결과를 리스너에게 브로드캐스트합니다.

#### 메서드

- `__init__(self, tasks, listener_manager, get_intervention_func, complete_task_func, error_task_func)` (줄 27): Args:
- `async start_execution(self, client_id, request_id, claude_runner, resource_manager)` (줄 49): 태스크의 Claude 실행을 백그라운드에서 시작
- `async _run_execution(self, task, claude_runner, resource_manager)` (줄 93): 백그라운드에서 Claude 실행 및 이벤트 브로드캐스트
- `is_execution_running(self, client_id, request_id)` (줄 178): 태스크 실행이 진행 중인지 확인
- `async send_reconnect_status(self, client_id, request_id, queue)` (줄 184): 재연결 시 현재 상태 이벤트 전송
- `async cancel_running_tasks(self, timeout)` (줄 218): 실행 중인 모든 태스크 취소

## 내부 의존성

- `seosoyoung.soul.service.task_models.Task`
- `seosoyoung.soul.service.task_models.TaskStatus`
