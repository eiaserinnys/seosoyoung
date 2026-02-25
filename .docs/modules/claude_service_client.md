# claude/service_client.py

> 경로: `seosoyoung/slackbot/claude/service_client.py`

## 개요

Claude Soul Service HTTP + SSE 클라이언트

seosoyoung-soul 서버와 통신하는 HTTP 클라이언트.
CLAUDE_EXECUTION_MODE=remote일 때 사용됩니다.

dorothy-bot의 claude_service_client.py 패턴을 seosoyoung에 맞게 적응.

## 클래스

### `SSEEvent`
- 위치: 줄 32
- 설명: Server-Sent Event 데이터

### `ExecuteResult`
- 위치: 줄 39
- 설명: soul 서버 실행 결과

### `SoulServiceError` (Exception)
- 위치: 줄 49
- 설명: Soul Service 클라이언트 오류

### `TaskConflictError` (SoulServiceError)
- 위치: 줄 54
- 설명: 태스크 충돌 오류 (이미 실행 중인 태스크 존재)

### `TaskNotFoundError` (SoulServiceError)
- 위치: 줄 59
- 설명: 태스크를 찾을 수 없음

### `TaskNotRunningError` (SoulServiceError)
- 위치: 줄 64
- 설명: 태스크가 실행 중이 아님

### `RateLimitError` (SoulServiceError)
- 위치: 줄 69
- 설명: 동시 실행 제한 초과

### `ConnectionLostError` (SoulServiceError)
- 위치: 줄 74
- 설명: SSE 연결 끊김 (재시도 실패)

### `ExponentialBackoff`
- 위치: 줄 81
- 설명: 지수 백오프 유틸리티

#### 메서드

- `__init__(self, base_delay, max_delay, max_retries)` (줄 84): 
- `get_delay(self)` (줄 95): 
- `should_retry(self)` (줄 99): 
- `increment(self)` (줄 102): 
- `reset(self)` (줄 105): 

### `SoulServiceClient`
- 위치: 줄 111
- 설명: seosoyoung-soul 서버 HTTP + SSE 클라이언트

Task API를 사용하여 Claude Code를 원격 실행합니다.

사용 예:
    client = SoulServiceClient(base_url="http://localhost:3105", token="xxx")
    result = await client.execute(
        client_id="seosoyoung_bot",
        request_id="thread_ts",
        prompt="안녕"
    )

#### 메서드

- `__init__(self, base_url, token)` (줄 125): 
- `is_configured(self)` (줄 131): 
- `async _get_session(self)` (줄 134): 
- `_build_headers(self)` (줄 147): 
- `async close(self)` (줄 156): 
- `async __aenter__(self)` (줄 161): 
- `async __aexit__(self, exc_type, exc_val, exc_tb)` (줄 164): 
- `async execute(self, client_id, request_id, prompt, resume_session_id, on_progress, on_compact, on_debug)` (줄 169): Claude Code 실행 (SSE 스트리밍, 연결 끊김 시 자동 재연결)
- `async intervene(self, client_id, request_id, text, user)` (줄 265): 실행 중인 태스크에 개입 메시지 전송
- `async ack(self, client_id, request_id)` (줄 293): 결과 수신 확인
- `async reconnect_stream(self, client_id, request_id, on_progress, on_compact, on_debug)` (줄 307): 태스크 SSE 스트림에 재연결
- `async health_check(self)` (줄 335): 헬스 체크
- `async _handle_sse_events(self, response, on_progress, on_compact, on_debug)` (줄 348): SSE 이벤트 스트림 처리
- `async _parse_sse_stream(self, response)` (줄 413): SSE 스트림 파싱
- `async _parse_error(self, response)` (줄 464): 에러 응답 파싱
