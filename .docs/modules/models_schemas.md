# models/schemas.py

> 경로: `seosoyoung/soul/models/schemas.py`

## 개요

Pydantic 모델 - Request/Response 스키마

## 클래스

### `SSEEventType` (str, Enum)
- 위치: 줄 13
- 설명: SSE 이벤트 타입

### `InterveneRequest` (BaseModel)
- 위치: 줄 34
- 설명: 개입 메시지 요청 (Task API 호환)

### `InterveneResponse` (BaseModel)
- 위치: 줄 43
- 설명: 개입 메시지 응답

### `AttachmentUploadResponse` (BaseModel)
- 위치: 줄 49
- 설명: 첨부 파일 업로드 응답

### `AttachmentCleanupResponse` (BaseModel)
- 위치: 줄 57
- 설명: 첨부 파일 정리 응답

### `HealthResponse` (BaseModel)
- 위치: 줄 63
- 설명: 헬스 체크 응답

### `ErrorDetail` (BaseModel)
- 위치: 줄 73
- 설명: 에러 상세 정보

### `ErrorResponse` (BaseModel)
- 위치: 줄 80
- 설명: 에러 응답

### `SessionEvent` (BaseModel)
- 위치: 줄 87
- 설명: 세션 ID 조기 통지 이벤트

Claude Code 세션이 시작되면 session_id를 클라이언트에 즉시 알립니다.
클라이언트는 이 session_id로 인터벤션 API를 호출할 수 있습니다.

### `ProgressEvent` (BaseModel)
- 위치: 줄 97
- 설명: 진행 상황 이벤트

### `MemoryEvent` (BaseModel)
- 위치: 줄 103
- 설명: 메모리 사용량 이벤트

### `InterventionSentEvent` (BaseModel)
- 위치: 줄 111
- 설명: 개입 메시지 전송 확인 이벤트

### `CompleteEvent` (BaseModel)
- 위치: 줄 118
- 설명: 실행 완료 이벤트

### `ErrorEvent` (BaseModel)
- 위치: 줄 126
- 설명: 오류 이벤트

### `ContextUsageEvent` (BaseModel)
- 위치: 줄 133
- 설명: 컨텍스트 사용량 이벤트

### `CompactEvent` (BaseModel)
- 위치: 줄 141
- 설명: 컴팩트 실행 이벤트

### `DebugEvent` (BaseModel)
- 위치: 줄 148
- 설명: 디버그 정보 이벤트 (rate_limit 경고 등)

### `TaskStatus` (str, Enum)
- 위치: 줄 156
- 설명: 태스크 상태

### `ExecuteRequest` (BaseModel)
- 위치: 줄 163
- 설명: 실행 요청

### `TaskResponse` (BaseModel)
- 위치: 줄 175
- 설명: 태스크 정보 응답

### `TaskListResponse` (BaseModel)
- 위치: 줄 188
- 설명: 태스크 목록 응답

### `TaskInterveneRequest` (BaseModel)
- 위치: 줄 193
- 설명: 개입 메시지 요청

### `ThinkingStartSSEEvent` (BaseModel)
- 위치: 줄 202
- 설명: 사고 블록 시작 이벤트

TextBlock 하나를 '카드'로 추상화하여 시작 시점을 알립니다.

### `ThinkingDeltaSSEEvent` (BaseModel)
- 위치: 줄 211
- 설명: 사고 텍스트 이벤트

TextBlock의 전체 텍스트 내용. SDK가 청크 스트리밍을 지원하지
않으므로 한 번에 전체 텍스트가 전달됩니다.

### `ThinkingEndSSEEvent` (BaseModel)
- 위치: 줄 222
- 설명: 사고 블록 완료 이벤트

### `ToolStartSSEEvent` (BaseModel)
- 위치: 줄 228
- 설명: 도구 호출 시작 이벤트

### `ToolResultSSEEvent` (BaseModel)
- 위치: 줄 236
- 설명: 도구 결과 이벤트

### `ResultSSEEvent` (BaseModel)
- 위치: 줄 245
- 설명: 엔진 최종 결과 이벤트 (dashboard 전용)

CompleteEvent/ErrorEvent와 병행 발행됩니다.
슬랙봇은 CompleteEvent/ErrorEvent를 소비하고,
대시보드는 ResultSSEEvent를 소비합니다.

### `StateChangeSSEEvent` (BaseModel)
- 위치: 줄 258
- 설명: 엔진 상태 전환 이벤트
