# models/schemas.py

> 경로: `seosoyoung/soul/models/schemas.py`

## 개요

Pydantic 모델 - Request/Response 스키마

## 클래스

### `SSEEventType` (str, Enum)
- 위치: 줄 13
- 설명: SSE 이벤트 타입

### `InterveneRequest` (BaseModel)
- 위치: 줄 26
- 설명: 개입 메시지 요청 (Task API 호환)

### `InterveneResponse` (BaseModel)
- 위치: 줄 35
- 설명: 개입 메시지 응답

### `AttachmentUploadResponse` (BaseModel)
- 위치: 줄 41
- 설명: 첨부 파일 업로드 응답

### `AttachmentCleanupResponse` (BaseModel)
- 위치: 줄 49
- 설명: 첨부 파일 정리 응답

### `HealthResponse` (BaseModel)
- 위치: 줄 55
- 설명: 헬스 체크 응답

### `ErrorDetail` (BaseModel)
- 위치: 줄 65
- 설명: 에러 상세 정보

### `ErrorResponse` (BaseModel)
- 위치: 줄 72
- 설명: 에러 응답

### `SessionEvent` (BaseModel)
- 위치: 줄 79
- 설명: 세션 ID 조기 통지 이벤트

Claude Code 세션이 시작되면 session_id를 클라이언트에 즉시 알립니다.
클라이언트는 이 session_id로 인터벤션 API를 호출할 수 있습니다.

### `ProgressEvent` (BaseModel)
- 위치: 줄 89
- 설명: 진행 상황 이벤트

### `MemoryEvent` (BaseModel)
- 위치: 줄 95
- 설명: 메모리 사용량 이벤트

### `InterventionSentEvent` (BaseModel)
- 위치: 줄 103
- 설명: 개입 메시지 전송 확인 이벤트

### `CompleteEvent` (BaseModel)
- 위치: 줄 110
- 설명: 실행 완료 이벤트

### `ErrorEvent` (BaseModel)
- 위치: 줄 118
- 설명: 오류 이벤트

### `ContextUsageEvent` (BaseModel)
- 위치: 줄 125
- 설명: 컨텍스트 사용량 이벤트

### `CompactEvent` (BaseModel)
- 위치: 줄 133
- 설명: 컴팩트 실행 이벤트

### `DebugEvent` (BaseModel)
- 위치: 줄 140
- 설명: 디버그 정보 이벤트 (rate_limit 경고 등)

### `TaskStatus` (str, Enum)
- 위치: 줄 148
- 설명: 태스크 상태

### `ExecuteRequest` (BaseModel)
- 위치: 줄 155
- 설명: 실행 요청

### `TaskResponse` (BaseModel)
- 위치: 줄 167
- 설명: 태스크 정보 응답

### `TaskListResponse` (BaseModel)
- 위치: 줄 180
- 설명: 태스크 목록 응답

### `TaskInterveneRequest` (BaseModel)
- 위치: 줄 185
- 설명: 개입 메시지 요청
