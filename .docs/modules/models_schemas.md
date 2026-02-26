# models/schemas.py

> 경로: `seosoyoung/soul/models/schemas.py`

## 개요

Pydantic 모델 - Request/Response 스키마

## 클래스

### `SSEEventType` (str, Enum)
- 위치: 줄 13
- 설명: SSE 이벤트 타입

### `InterveneRequest` (BaseModel)
- 위치: 줄 33
- 설명: 개입 메시지 요청 (Task API 호환)

### `InterveneResponse` (BaseModel)
- 위치: 줄 42
- 설명: 개입 메시지 응답

### `AttachmentUploadResponse` (BaseModel)
- 위치: 줄 48
- 설명: 첨부 파일 업로드 응답

### `AttachmentCleanupResponse` (BaseModel)
- 위치: 줄 56
- 설명: 첨부 파일 정리 응답

### `HealthResponse` (BaseModel)
- 위치: 줄 62
- 설명: 헬스 체크 응답

### `ErrorDetail` (BaseModel)
- 위치: 줄 72
- 설명: 에러 상세 정보

### `ErrorResponse` (BaseModel)
- 위치: 줄 79
- 설명: 에러 응답

### `SessionEvent` (BaseModel)
- 위치: 줄 86
- 설명: 세션 ID 조기 통지 이벤트

Claude Code 세션이 시작되면 session_id를 클라이언트에 즉시 알립니다.
클라이언트는 이 session_id로 인터벤션 API를 호출할 수 있습니다.

### `ProgressEvent` (BaseModel)
- 위치: 줄 96
- 설명: 진행 상황 이벤트

### `MemoryEvent` (BaseModel)
- 위치: 줄 102
- 설명: 메모리 사용량 이벤트

### `InterventionSentEvent` (BaseModel)
- 위치: 줄 110
- 설명: 개입 메시지 전송 확인 이벤트

### `CompleteEvent` (BaseModel)
- 위치: 줄 117
- 설명: 실행 완료 이벤트

### `ErrorEvent` (BaseModel)
- 위치: 줄 125
- 설명: 오류 이벤트

### `ContextUsageEvent` (BaseModel)
- 위치: 줄 132
- 설명: 컨텍스트 사용량 이벤트

### `CompactEvent` (BaseModel)
- 위치: 줄 140
- 설명: 컴팩트 실행 이벤트

### `DebugEvent` (BaseModel)
- 위치: 줄 147
- 설명: 디버그 정보 이벤트 (rate_limit 경고 등)

### `TaskStatus` (str, Enum)
- 위치: 줄 155
- 설명: 태스크 상태

### `ExecuteRequest` (BaseModel)
- 위치: 줄 162
- 설명: 실행 요청

### `TaskResponse` (BaseModel)
- 위치: 줄 174
- 설명: 태스크 정보 응답

### `TaskListResponse` (BaseModel)
- 위치: 줄 187
- 설명: 태스크 목록 응답

### `TaskInterveneRequest` (BaseModel)
- 위치: 줄 192
- 설명: 개입 메시지 요청

### `TextStartSSEEvent` (BaseModel)
- 위치: 줄 205
- 설명: 텍스트 블록 시작 이벤트

AssistantMessage의 TextBlock 하나를 '카드'로 추상화하여
시작 시점을 알립니다.

### `TextDeltaSSEEvent` (BaseModel)
- 위치: 줄 215
- 설명: 텍스트 블록 내용 이벤트

TextBlock의 전체 텍스트 내용. SDK가 청크 스트리밍을 지원하지
않으므로 한 번에 전체 텍스트가 전달됩니다.

### `TextEndSSEEvent` (BaseModel)
- 위치: 줄 226
- 설명: 텍스트 블록 완료 이벤트

### `ToolStartSSEEvent` (BaseModel)
- 위치: 줄 232
- 설명: 도구 호출 시작 이벤트

### `ToolResultSSEEvent` (BaseModel)
- 위치: 줄 240
- 설명: 도구 결과 이벤트

### `ResultSSEEvent` (BaseModel)
- 위치: 줄 249
- 설명: 엔진 최종 결과 이벤트 (dashboard 전용)

CompleteEvent/ErrorEvent와 병행 발행됩니다.
슬랙봇은 CompleteEvent/ErrorEvent를 소비하고,
대시보드는 ResultSSEEvent를 소비합니다.
