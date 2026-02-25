# models/schemas.py

> 경로: `seosoyoung/soul/models/schemas.py`

## 개요

Pydantic 모델 - Request/Response 스키마

## 클래스

### `SSEEventType` (str, Enum)
- 위치: 줄 13
- 설명: SSE 이벤트 타입

### `InterveneRequest` (BaseModel)
- 위치: 줄 25
- 설명: 개입 메시지 요청 (Task API 호환)

### `InterveneResponse` (BaseModel)
- 위치: 줄 34
- 설명: 개입 메시지 응답

### `AttachmentUploadResponse` (BaseModel)
- 위치: 줄 40
- 설명: 첨부 파일 업로드 응답

### `AttachmentCleanupResponse` (BaseModel)
- 위치: 줄 48
- 설명: 첨부 파일 정리 응답

### `HealthResponse` (BaseModel)
- 위치: 줄 54
- 설명: 헬스 체크 응답

### `ErrorDetail` (BaseModel)
- 위치: 줄 64
- 설명: 에러 상세 정보

### `ErrorResponse` (BaseModel)
- 위치: 줄 71
- 설명: 에러 응답

### `ProgressEvent` (BaseModel)
- 위치: 줄 78
- 설명: 진행 상황 이벤트

### `MemoryEvent` (BaseModel)
- 위치: 줄 84
- 설명: 메모리 사용량 이벤트

### `InterventionSentEvent` (BaseModel)
- 위치: 줄 92
- 설명: 개입 메시지 전송 확인 이벤트

### `CompleteEvent` (BaseModel)
- 위치: 줄 99
- 설명: 실행 완료 이벤트

### `ErrorEvent` (BaseModel)
- 위치: 줄 107
- 설명: 오류 이벤트

### `ContextUsageEvent` (BaseModel)
- 위치: 줄 114
- 설명: 컨텍스트 사용량 이벤트

### `CompactEvent` (BaseModel)
- 위치: 줄 122
- 설명: 컴팩트 실행 이벤트

### `DebugEvent` (BaseModel)
- 위치: 줄 129
- 설명: 디버그 정보 이벤트 (rate_limit 경고 등)

### `TaskStatus` (str, Enum)
- 위치: 줄 137
- 설명: 태스크 상태

### `ExecuteRequest` (BaseModel)
- 위치: 줄 144
- 설명: 실행 요청

### `TaskResponse` (BaseModel)
- 위치: 줄 156
- 설명: 태스크 정보 응답

### `TaskListResponse` (BaseModel)
- 위치: 줄 169
- 설명: 태스크 목록 응답

### `TaskInterveneRequest` (BaseModel)
- 위치: 줄 174
- 설명: 개입 메시지 요청
