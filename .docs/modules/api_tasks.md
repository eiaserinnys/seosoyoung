# api/tasks.py

> 경로: `seosoyoung/soul/api/tasks.py`

## 개요

Tasks API - 태스크 기반 API 엔드포인트

기존 세션 기반 API를 대체하는 새 API.
클라이언트 재시작 시에도 결과를 복구할 수 있도록 설계됨.

## 함수

### `task_to_response(task)`
- 위치: 줄 40
- 설명: Task를 TaskResponse로 변환

### `async execute_task(request, _)`
- 위치: 줄 63
- 데코레이터: router.post
- 설명: Claude Code 실행 (SSE 스트리밍)

태스크를 생성하고 Claude Code를 백그라운드에서 실행합니다.
결과는 SSE로 스트리밍되며, 클라이언트 연결이 끊어져도
백그라운드 실행은 계속되고 결과는 보관되어 나중에 조회할 수 있습니다.

### `async get_tasks(client_id, _)`
- 위치: 줄 159
- 데코레이터: router.get
- 설명: 클라이언트의 태스크 목록 조회

클라이언트가 재시작 후 미전달 결과를 확인하는 데 사용합니다.

### `async get_task(client_id, request_id, _)`
- 위치: 줄 181
- 데코레이터: router.get
- 설명: 특정 태스크 조회

### `async reconnect_stream(client_id, request_id, _, last_event_id)`
- 위치: 줄 211
- 데코레이터: router.get
- 설명: 태스크 SSE 스트림에 재연결

running 태스크: 현재 상태 전송 후 진행 중인 이벤트를 계속 수신
completed 태스크: 저장된 결과를 즉시 반환
error 태스크: 저장된 에러를 즉시 반환

Last-Event-ID 헤더가 있으면 해당 ID 이후의 미수신 이벤트를 재전송합니다.

### `async ack_task(client_id, request_id, _)`
- 위치: 줄 317
- 데코레이터: router.post
- 설명: 결과 수신 확인

클라이언트가 결과를 성공적으로 수신했음을 알립니다.
확인된 태스크는 서버에서 삭제됩니다.

### `async intervene_task(client_id, request_id, request, _)`
- 위치: 줄 355
- 데코레이터: router.post
- 설명: 실행 중인 태스크에 개입 메시지 전송

running 상태의 태스크에만 메시지를 전송할 수 있습니다.

### `async intervene_by_session(session_id, request, _)`
- 위치: 줄 416
- 데코레이터: router.post
- 설명: session_id 기반 개입 메시지 전송

Claude Code session_id로 실행 중인 태스크를 찾아 개입 메시지를 전송합니다.
기존 client_id/request_id 기반 API의 대안으로, 봇이 session_id만 알면
인터벤션을 보낼 수 있습니다.

## 내부 의존성

- `seosoyoung.soul.api.auth.verify_token`
- `seosoyoung.soul.models.ErrorResponse`
- `seosoyoung.soul.models.ExecuteRequest`
- `seosoyoung.soul.models.InterveneRequest`
- `seosoyoung.soul.models.InterveneResponse`
- `seosoyoung.soul.models.TaskInterveneRequest`
- `seosoyoung.soul.models.TaskListResponse`
- `seosoyoung.soul.models.TaskResponse`
- `seosoyoung.soul.service.resource_manager`
- `seosoyoung.soul.service.soul_engine`
- `seosoyoung.soul.service.task_manager.Task`
- `seosoyoung.soul.service.task_manager.TaskConflictError`
- `seosoyoung.soul.service.task_manager.TaskNotFoundError`
- `seosoyoung.soul.service.task_manager.TaskNotRunningError`
- `seosoyoung.soul.service.task_manager.TaskStatus`
- `seosoyoung.soul.service.task_manager.get_task_manager`
