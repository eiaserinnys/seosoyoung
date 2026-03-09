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

Attributes:
    agent_session_id: init 이벤트에서 확보한 세션 ID (없으면 None).
        _handle_sse_events에서 init 이후 연결이 끊긴 경우 이 값이 설정되어
        execute()에서 재연결에 활용할 수 있습니다.

#### 메서드

- `__init__(self, message, agent_session_id)` (줄 81): 

### `ExponentialBackoff`
- 위치: 줄 88
- 설명: 지수 백오프 유틸리티

#### 메서드

- `__init__(self, base_delay, max_delay, max_retries)` (줄 91): 
- `get_delay(self)` (줄 102): 
- `should_retry(self)` (줄 106): 
- `increment(self)` (줄 109): 
- `reset(self)` (줄 112): 

### `SoulServiceClient`
- 위치: 줄 118
- 설명: Soulstream 서버 HTTP + SSE 클라이언트

per-session API를 사용하여 Claude Code를 원격 실행합니다.
agent_session_id가 유일한 식별자입니다.

사용 예:
    client = SoulServiceClient(base_url="http://localhost:4105", token="xxx")
    result = await client.execute(prompt="안녕")

#### 메서드

- `__init__(self, base_url, token)` (줄 129): 
- `is_configured(self)` (줄 135): 
- `async _get_session(self)` (줄 138): 
- `_build_headers(self)` (줄 152): 
- `async close(self)` (줄 161): 
- `async __aenter__(self)` (줄 166): 
- `async __aexit__(self, exc_type, exc_val, exc_tb)` (줄 169): 
- `async execute(self, prompt, agent_session_id, on_compact, on_debug, on_session, on_credential_alert)` (줄 174): Claude Code 실행 (SSE 스트리밍, 연결 끊김 시 자동 재연결)
- `async intervene(self, agent_session_id, text, user)` (줄 307): 세션에 개입 메시지 전송
- `async reconnect_stream(self, agent_session_id, on_compact, on_debug, on_credential_alert)` (줄 343): 세션 SSE 스트림에 재연결
- `async respond_to_input_request(self, agent_session_id, request_id, answers)` (줄 389): AskUserQuestion에 대한 사용자 응답 전달
- `async health_check(self)` (줄 438): 헬스 체크
- `async list_profiles(self)` (줄 451): 프로필 목록 조회 (GET /profiles)
- `async get_rate_limits(self)` (줄 466): 전체 프로필 rate limit 조회 (GET /profiles/rate-limits)
- `async save_profile(self, name)` (줄 484): 현재 크레덴셜을 프로필로 저장 (POST /profiles/{name})
- `async activate_profile(self, name)` (줄 499): 프로필 활성화 (POST /profiles/{name}/activate)
- `async delete_profile(self, name)` (줄 516): 프로필 삭제 (DELETE /profiles/{name})
- `async get_current_email(self)` (줄 533): 현재 크레덴셜의 계정 이메일 조회 (GET /profiles/email)
- `async _handle_sse_events(self, response, on_compact, on_debug, on_session, on_credential_alert, on_thinking, on_text_start, on_text_delta, on_text_end, on_tool_start, on_tool_result, on_input_request)` (줄 553): SSE 이벤트 스트림 처리
- `async _parse_sse_stream(self, response)` (줄 710): SSE 스트림 파싱
- `async _parse_error(self, response)` (줄 785): 에러 응답 파싱
