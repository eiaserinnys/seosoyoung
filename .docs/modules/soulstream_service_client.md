# soulstream/service_client.py

> 경로: `seosoyoung/slackbot/soulstream/service_client.py`

## 개요

Soulstream Service HTTP + SSE 클라이언트

Soulstream 서버(독립 soul-server, 기본 포트 4105)와 통신하는 HTTP 클라이언트.
per-session 아키텍처: agent_session_id가 유일한 식별자.

## 클래스

### `SSEEvent`
- 위치: 줄 29
- 설명: Server-Sent Event 데이터

### `ExecuteResult`
- 위치: 줄 37
- 설명: Soulstream 서버 실행 결과

### `SoulServiceError` (Exception)
- 위치: 줄 48
- 설명: Soul Service 클라이언트 오류

### `SessionConflictError` (SoulServiceError)
- 위치: 줄 53
- 설명: 세션 충돌 오류 (이미 실행 중인 세션)

### `SessionNotFoundError` (SoulServiceError)
- 위치: 줄 58
- 설명: 세션을 찾을 수 없음

### `SessionNotRunningError` (SoulServiceError)
- 위치: 줄 63
- 설명: 세션이 실행 중이 아님

### `RateLimitError` (SoulServiceError)
- 위치: 줄 68
- 설명: 동시 실행 제한 초과

### `ConnectionLostError` (SoulServiceError)
- 위치: 줄 73
- 설명: SSE 연결 끊김 (재시도 실패)

### `ExponentialBackoff`
- 위치: 줄 80
- 설명: 지수 백오프 유틸리티

#### 메서드

- `__init__(self, base_delay, max_delay, max_retries)` (줄 83): 
- `get_delay(self)` (줄 94): 
- `should_retry(self)` (줄 98): 
- `increment(self)` (줄 101): 
- `reset(self)` (줄 104): 

### `SoulServiceClient`
- 위치: 줄 110
- 설명: Soulstream 서버 HTTP + SSE 클라이언트

per-session API를 사용하여 Claude Code를 원격 실행합니다.
agent_session_id가 유일한 식별자입니다.

사용 예:
    client = SoulServiceClient(base_url="http://localhost:4105", token="xxx")
    result = await client.execute(prompt="안녕")

#### 메서드

- `__init__(self, base_url, token)` (줄 121): 
- `is_configured(self)` (줄 127): 
- `async _get_session(self)` (줄 130): 
- `_build_headers(self)` (줄 143): 
- `async close(self)` (줄 152): 
- `async __aenter__(self)` (줄 157): 
- `async __aexit__(self, exc_type, exc_val, exc_tb)` (줄 160): 
- `async execute(self, prompt, agent_session_id, on_progress, on_compact, on_debug, on_session, on_credential_alert)` (줄 165): Claude Code 실행 (SSE 스트리밍, 연결 끊김 시 자동 재연결)
- `async intervene(self, agent_session_id, text, user)` (줄 296): 세션에 개입 메시지 전송
- `async reconnect_stream(self, agent_session_id, on_progress, on_compact, on_debug, on_credential_alert)` (줄 332): 세션 SSE 스트림에 재연결
- `async health_check(self)` (줄 378): 헬스 체크
- `async list_profiles(self)` (줄 391): 프로필 목록 조회 (GET /profiles)
- `async get_rate_limits(self)` (줄 406): 전체 프로필 rate limit 조회 (GET /profiles/rate-limits)
- `async save_profile(self, name)` (줄 424): 현재 크레덴셜을 프로필로 저장 (POST /profiles/{name})
- `async activate_profile(self, name)` (줄 439): 프로필 활성화 (POST /profiles/{name}/activate)
- `async delete_profile(self, name)` (줄 456): 프로필 삭제 (DELETE /profiles/{name})
- `async get_current_email(self)` (줄 473): 현재 크레덴셜의 계정 이메일 조회 (GET /profiles/email)
- `async _handle_sse_events(self, response, on_progress, on_compact, on_debug, on_session, on_credential_alert, on_thinking, on_text_start, on_text_delta, on_text_end, on_tool_start, on_tool_result)` (줄 493): SSE 이벤트 스트림 처리
- `async _parse_sse_stream(self, response)` (줄 640): SSE 스트림 파싱
- `async _parse_error(self, response)` (줄 701): 에러 응답 파싱
