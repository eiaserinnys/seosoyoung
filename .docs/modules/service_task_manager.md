# service/task_manager.py

> 경로: `seosoyoung/soul/service/task_manager.py`

## 개요

TaskManager - 태스크 라이프사이클 관리

태스크 기반 아키텍처의 핵심 컴포넌트.
클라이언트(seosoyoung_bot 등)의 실행 요청을 태스크로 관리하고,
결과를 영속화하여 클라이언트 재시작 시에도 복구 가능하게 합니다.

이 모듈은 다음 서브모듈들을 조합합니다:
- task_models: 데이터 모델 및 예외
- task_storage: JSON 영속화
- task_listener: SSE 리스너 관리
- task_executor: 백그라운드 실행

## 클래스

### `TaskManager`
- 위치: 줄 52
- 설명: 태스크 라이프사이클 관리자

역할:
1. 태스크 생성/조회/삭제
2. {client_id, request_id}로 활성 태스크 추적 (중복 방지)
3. 태스크 상태 업데이트 및 결과 저장
4. SSE 리스너 관리 (via TaskListenerManager)
5. 개입 메시지 큐 관리
6. JSON 파일 영속화 (via TaskStorage)
7. 백그라운드 실행 (via TaskExecutor)

#### 메서드

- `__init__(self, storage_path)` (줄 66): Args:
- `register_session(self, session_id, client_id, request_id)` (줄 91): session_id → task_key 매핑 등록
- `get_task_by_session(self, session_id)` (줄 100): session_id로 태스크 조회
- `_unregister_session_for_task(self, key)` (줄 107): task_key에 해당하는 session_id 인덱스 제거
- `async load(self)` (줄 116): 파일에서 태스크 로드
- `async save(self)` (줄 120): 태스크 상태 저장
- `async _schedule_save(self)` (줄 124): 저장 예약 (debounce)
- `get_running_tasks(self)` (줄 130): 실행 중인 태스크 목록 반환
- `async create_task(self, client_id, request_id, prompt, resume_session_id, allowed_tools, disallowed_tools, use_mcp)` (줄 134): 새 태스크 생성
- `async get_task(self, client_id, request_id)` (줄 187): 태스크 조회
- `async get_tasks_by_client(self, client_id)` (줄 192): 클라이언트별 태스크 목록 조회
- `async _complete_task_internal(self, client_id, request_id, result, claude_session_id)` (줄 199): 태스크 완료 처리 (내부용 - executor에서 호출)
- `async complete_task(self, client_id, request_id, result, claude_session_id)` (줄 209): 태스크 완료 처리
- `async _error_task_internal(self, client_id, request_id, error)` (줄 249): 태스크 에러 처리 (내부용 - executor에서 호출)
- `async error_task(self, client_id, request_id, error)` (줄 258): 태스크 에러 처리
- `async ack_task(self, client_id, request_id)` (줄 295): 결과 수신 확인 (태스크 삭제)
- `async mark_delivered(self, client_id, request_id)` (줄 326): 결과 전달 완료 마킹
- `async add_listener(self, client_id, request_id, queue)` (줄 350): SSE 리스너 추가
- `async remove_listener(self, client_id, request_id, queue)` (줄 355): SSE 리스너 제거
- `async broadcast(self, client_id, request_id, event)` (줄 360): 모든 리스너에게 이벤트 브로드캐스트
- `async add_intervention_by_session(self, session_id, text, user, attachment_paths)` (줄 366): session_id 기반 개입 메시지 추가
- `async add_intervention(self, client_id, request_id, text, user, attachment_paths)` (줄 404): 개입 메시지 추가
- `async get_intervention(self, client_id, request_id)` (줄 447): 개입 메시지 가져오기 (non-blocking)
- `async start_execution(self, client_id, request_id, claude_runner, resource_manager)` (줄 466): 태스크의 Claude 실행을 백그라운드에서 시작
- `is_execution_running(self, client_id, request_id)` (줄 478): 태스크 실행이 진행 중인지 확인
- `async send_reconnect_status(self, client_id, request_id, queue)` (줄 482): 재연결 시 현재 상태 이벤트 전송
- `async cancel_running_tasks(self, timeout)` (줄 493): 실행 중인 모든 태스크 취소
- `async cleanup_old_tasks(self, max_age_hours)` (줄 498): 오래된 태스크 정리
- `_clear_queue(self, queue)` (줄 544): 큐 내 모든 항목 제거
- `get_stats(self)` (줄 552): 통계 반환

## 함수

### `get_task_manager()`
- 위치: 줄 570
- 설명: TaskManager 싱글톤 반환

### `init_task_manager(storage_path)`
- 위치: 줄 578
- 설명: TaskManager 초기화

### `set_task_manager(manager)`
- 위치: 줄 585
- 설명: TaskManager 인스턴스 설정 (테스트용)

## 내부 의존성

- `seosoyoung.soul.service.task_executor.TaskExecutor`
- `seosoyoung.soul.service.task_listener.TaskListenerManager`
- `seosoyoung.soul.service.task_models.Task`
- `seosoyoung.soul.service.task_models.TaskConflictError`
- `seosoyoung.soul.service.task_models.TaskNotFoundError`
- `seosoyoung.soul.service.task_models.TaskNotRunningError`
- `seosoyoung.soul.service.task_models.TaskStatus`
- `seosoyoung.soul.service.task_models.utc_now`
- `seosoyoung.soul.service.task_storage.TaskStorage`
