# models/schemas.py

> 경로: `seosoyoung/soul/models/schemas.py`

## 개요

Pydantic 모델 - Request/Response 스키마

## 클래스

### `SSEEventType` (str, Enum)
- 위치: 줄 13
- 설명: SSE 이벤트 타입

### `InterveneRequest` (BaseModel)
- 위치: 줄 35
- 설명: 개입 메시지 요청 (Task API 호환)

### `InterveneResponse` (BaseModel)
- 위치: 줄 44
- 설명: 개입 메시지 응답

### `AttachmentUploadResponse` (BaseModel)
- 위치: 줄 50
- 설명: 첨부 파일 업로드 응답

### `AttachmentCleanupResponse` (BaseModel)
- 위치: 줄 58
- 설명: 첨부 파일 정리 응답

### `HealthResponse` (BaseModel)
- 위치: 줄 64
- 설명: 헬스 체크 응답

### `ErrorDetail` (BaseModel)
- 위치: 줄 74
- 설명: 에러 상세 정보

### `ErrorResponse` (BaseModel)
- 위치: 줄 81
- 설명: 에러 응답

### `SessionEvent` (BaseModel)
- 위치: 줄 88
- 설명: 세션 ID 조기 통지 이벤트

Claude Code 세션이 시작되면 session_id를 클라이언트에 즉시 알립니다.
클라이언트는 이 session_id로 인터벤션 API를 호출할 수 있습니다.

### `ProgressEvent` (BaseModel)
- 위치: 줄 98
- 설명: 진행 상황 이벤트

### `MemoryEvent` (BaseModel)
- 위치: 줄 104
- 설명: 메모리 사용량 이벤트

### `InterventionSentEvent` (BaseModel)
- 위치: 줄 112
- 설명: 개입 메시지 전송 확인 이벤트

### `CompleteEvent` (BaseModel)
- 위치: 줄 119
- 설명: 실행 완료 이벤트

### `ErrorEvent` (BaseModel)
- 위치: 줄 127
- 설명: 오류 이벤트

### `ContextUsageEvent` (BaseModel)
- 위치: 줄 134
- 설명: 컨텍스트 사용량 이벤트

### `CompactEvent` (BaseModel)
- 위치: 줄 142
- 설명: 컴팩트 실행 이벤트

### `DebugEvent` (BaseModel)
- 위치: 줄 149
- 설명: 디버그 정보 이벤트 (rate_limit 경고 등)

### `TaskStatus` (str, Enum)
- 위치: 줄 157
- 설명: 태스크 상태

### `ExecuteRequest` (BaseModel)
- 위치: 줄 164
- 설명: 실행 요청

### `TaskResponse` (BaseModel)
- 위치: 줄 176
- 설명: 태스크 정보 응답

### `TaskListResponse` (BaseModel)
- 위치: 줄 189
- 설명: 태스크 목록 응답

### `TaskInterveneRequest` (BaseModel)
- 위치: 줄 194
- 설명: 개입 메시지 요청

### `TextStartSSEEvent` (BaseModel)
- 위치: 줄 207
- 설명: 텍스트 블록 시작 이벤트

AssistantMessage의 TextBlock 하나를 '카드'로 추상화하여
시작 시점을 알립니다.

### `TextDeltaSSEEvent` (BaseModel)
- 위치: 줄 217
- 설명: 텍스트 블록 내용 이벤트

TextBlock의 전체 텍스트 내용. SDK가 청크 스트리밍을 지원하지
않으므로 한 번에 전체 텍스트가 전달됩니다.

### `TextEndSSEEvent` (BaseModel)
- 위치: 줄 228
- 설명: 텍스트 블록 완료 이벤트

### `ToolStartSSEEvent` (BaseModel)
- 위치: 줄 234
- 설명: 도구 호출 시작 이벤트

### `ToolResultSSEEvent` (BaseModel)
- 위치: 줄 243
- 설명: 도구 결과 이벤트

### `ResultSSEEvent` (BaseModel)
- 위치: 줄 253
- 설명: 엔진 최종 결과 이벤트 (dashboard 전용)

CompleteEvent/ErrorEvent와 병행 발행됩니다.
슬랙봇은 CompleteEvent/ErrorEvent를 소비하고,
대시보드는 ResultSSEEvent를 소비합니다.

### `RateLimitState` (BaseModel)
- 위치: 줄 268
- 설명: 단일 rate limit 타입의 상태

### `ProfileRateLimitInfo` (BaseModel)
- 위치: 줄 274
- 설명: 프로필별 rate limit 정보

### `CredentialAlertEvent` (BaseModel)
- 위치: 줄 281
- 설명: 크레덴셜 rate limit 95% 도달 알림 이벤트

특정 프로필의 rate limit utilization이 95%에 도달하면
전체 프로필의 rate limit 현황과 함께 발행됩니다.
