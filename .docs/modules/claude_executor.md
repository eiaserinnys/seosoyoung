# claude/executor.py

> 경로: `seosoyoung/slackbot/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

Soulstream 서버(독립 soul-server)에 HTTP/SSE로 위임하여 실행합니다.

## 클래스

### `ClaudeExecutor`
- 위치: 줄 56
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, session_runtime, restart_manager, send_long_message, send_restart_confirmation, update_message_fn)` (줄 63): 
- `run(self, prompt, thread_ts, msg_ts)` (줄 128): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, thread_ts, prompt, msg_ts)` (줄 190): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_run_with_lock(self, thread_ts, prompt, msg_ts)` (줄 228): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, thread_ts, prompt, msg_ts)` (줄 281): 단일 Claude 실행 — Soulstream 서버에 위임
- `_get_role_config(self, role)` (줄 313): 역할에 맞는 runner 설정을 반환 (모듈 함수에 위임)
- `_get_service_adapter(self)` (줄 317): Remote 모드용 ClaudeServiceAdapter를 생성하여 반환 (호출마다 새 인스턴스)
- `_register_session_id(self, thread_ts, session_id)` (줄 337): thread_ts ↔ session_id 매핑 등록 및 버퍼된 인터벤션 flush
- `_unregister_session_id(self, thread_ts)` (줄 361): thread_ts ↔ session_id 매핑 해제
- `_get_session_id(self, thread_ts)` (줄 370): thread_ts에 대응하는 session_id 조회
- `_execute_remote(self, thread_ts, prompt)` (줄 375): Remote 모드: Soulstream 서버에 실행을 위임
- `_process_result(self, presentation, result, thread_ts)` (줄 447): 실행 결과 처리

## 함수

### `_get_mcp_config_path()`
- 위치: 줄 25
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

### `_get_role_config(role, role_tools)`
- 위치: 줄 31
- 설명: 역할에 맞는 runner 설정을 반환 (모듈 레벨 함수)

Args:
    role: 실행 역할 ("admin", "viewer" 등)
    role_tools: 역할별 허용 도구 딕셔너리

Returns:
    dict with keys: allowed_tools, disallowed_tools, mcp_config_path

## 내부 의존성

- `seosoyoung.slackbot.claude.engine_types.ClaudeResult`
- `seosoyoung.slackbot.claude.engine_types.CompactCallback`
- `seosoyoung.slackbot.claude.engine_types.ProgressCallback`
- `seosoyoung.slackbot.claude.intervention.InterventionManager`
- `seosoyoung.slackbot.claude.intervention.PendingPrompt`
- `seosoyoung.slackbot.claude.result_processor.ResultProcessor`
- `seosoyoung.slackbot.claude.session.SessionManager`
- `seosoyoung.slackbot.claude.session.SessionRuntime`
- `seosoyoung.slackbot.claude.types.UpdateMessageFn`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
