# soulstream/service_adapter.py

> 경로: `seosoyoung/slackbot/soulstream/service_adapter.py`

## 개요

Soulstream Service Adapter

SoulServiceClient를 통해 Soulstream 서버에 Claude Code 실행을 위임하고,
결과를 기존 ClaudeResult 포맷으로 변환합니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.

## 클래스

### `ClaudeServiceAdapter`
- 위치: 줄 25
- 설명: Soulstream 서버 어댑터

executor의 _execute_once에서 사용.
SoulServiceClient로 Soulstream에 실행을 위임하고 ClaudeResult로 변환합니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.
client_id, request_id는 사용하지 않습니다.

#### 메서드

- `__init__(self, client)` (줄 35): 
- `async execute(self, prompt, agent_session_id, on_compact, on_debug, on_session, on_credential_alert)` (줄 40): Claude Code를 Soulstream에서 실행하고 ClaudeResult로 반환
- `async intervene(self, agent_session_id, text, user)` (줄 148): 세션에 인터벤션 전송 (agent_session_id 기반)
- `async close(self)` (줄 177): 클라이언트 종료

## 내부 의존성

- `seosoyoung.slackbot.soulstream.engine_types.ClaudeResult`
- `seosoyoung.slackbot.soulstream.service_client.RateLimitError`
- `seosoyoung.slackbot.soulstream.service_client.SessionConflictError`
- `seosoyoung.slackbot.soulstream.service_client.SessionNotFoundError`
- `seosoyoung.slackbot.soulstream.service_client.SessionNotRunningError`
- `seosoyoung.slackbot.soulstream.service_client.SoulServiceClient`
- `seosoyoung.slackbot.soulstream.service_client.SoulServiceError`
