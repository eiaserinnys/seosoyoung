# claude/service_adapter.py

> 경로: `seosoyoung/slackbot/claude/service_adapter.py`

## 개요

Soulstream Service Adapter

SoulServiceClient를 통해 Soulstream 서버에 Claude Code 실행을 위임하고,
결과를 기존 ClaudeResult 포맷으로 변환합니다.

ClaudeExecutor에서 local/remote 분기 시 remote 경로로 사용됩니다.

## 클래스

### `ClaudeServiceAdapter`
- 위치: 줄 25
- 설명: Soulstream 서버 어댑터

executor의 _execute_once에서 remote 모드일 때 사용.
SoulServiceClient로 Soulstream에 실행을 위임하고 ClaudeResult로 변환합니다.

#### 메서드

- `__init__(self, client, client_id)` (줄 32): 
- `async execute(self, prompt, request_id, resume_session_id, on_progress, on_compact, on_debug, on_session, on_credential_alert)` (줄 38): Claude Code를 Soulstream에서 실행하고 ClaudeResult로 반환
- `async intervene(self, request_id, text, user)` (줄 139): 실행 중인 태스크에 인터벤션 전송 (client_id/request_id 기반, 폴백용)
- `async intervene_by_session(self, session_id, text, user)` (줄 166): session_id 기반 인터벤션 전송
- `async close(self)` (줄 192): 클라이언트 종료

## 내부 의존성

- `seosoyoung.slackbot.claude.engine_types.ClaudeResult`
- `seosoyoung.slackbot.claude.service_client.RateLimitError`
- `seosoyoung.slackbot.claude.service_client.SoulServiceClient`
- `seosoyoung.slackbot.claude.service_client.SoulServiceError`
- `seosoyoung.slackbot.claude.service_client.TaskConflictError`
- `seosoyoung.slackbot.claude.service_client.TaskNotFoundError`
- `seosoyoung.slackbot.claude.service_client.TaskNotRunningError`
