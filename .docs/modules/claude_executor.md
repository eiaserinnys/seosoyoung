# claude/executor.py

> 경로: `seosoyoung/slackbot/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

실행 모드 (execution_mode):
- local: 기존 방식. ClaudeRunner를 직접 사용하여 로컬에서 실행.
- remote: seosoyoung-soul 서버에 HTTP/SSE로 위임하여 실행.

## 클래스

### `ClaudeExecutor`
- 위치: 줄 34
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, session_runtime, restart_manager, send_long_message, send_restart_confirmation, update_message_fn)` (줄 41): 
- `run(self, prompt, thread_ts, msg_ts)` (줄 104): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, thread_ts, prompt, msg_ts)` (줄 166): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_run_with_lock(self, thread_ts, prompt, msg_ts)` (줄 204): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, thread_ts, prompt, msg_ts)` (줄 257): 단일 Claude 실행
- `_get_role_config(self, role)` (줄 326): 역할에 맞는 runner 설정을 반환
- `_get_service_adapter(self)` (줄 346): Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환
- `_execute_remote(self, thread_ts, prompt)` (줄 363): Remote 모드: soul 서버에 실행을 위임
- `_process_result(self, presentation, result, thread_ts)` (줄 405): 실행 결과 처리

## 함수

### `_get_mcp_config_path()`
- 위치: 줄 28
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

## 내부 의존성

- `seosoyoung.slackbot.claude.agent_runner.ClaudeResult`
- `seosoyoung.slackbot.claude.agent_runner.ClaudeRunner`
- `seosoyoung.slackbot.claude.engine_types.CompactCallback`
- `seosoyoung.slackbot.claude.engine_types.ProgressCallback`
- `seosoyoung.slackbot.claude.intervention.InterventionManager`
- `seosoyoung.slackbot.claude.intervention.PendingPrompt`
- `seosoyoung.slackbot.claude.result_processor.ResultProcessor`
- `seosoyoung.slackbot.claude.session.SessionManager`
- `seosoyoung.slackbot.claude.session.SessionRuntime`
- `seosoyoung.slackbot.claude.types.UpdateMessageFn`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
