# soulstream/executor.py

> 경로: `seosoyoung/slackbot/soulstream/executor.py`

## 개요

Claude Code 실행 로직

Soulstream 서버에 HTTP/SSE로 위임하여 Claude Code를 실행합니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
Soulstream에 interrupt를 전송하여 현재 실행을 중단시킵니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.

## 클래스

### `ClaudeExecutor`
- 위치: 줄 56
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

per-session 아키텍처: agent_session_id가 유일한 식별자.

#### 메서드

- `__init__(self, session_manager, session_runtime, restart_manager, send_long_message, send_restart_confirmation, update_message_fn)` (줄 65): 
- `run(self, prompt, thread_ts, msg_ts)` (줄 122): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, thread_ts, prompt, msg_ts)` (줄 201): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_run_with_lock(self, thread_ts, prompt, msg_ts)` (줄 237): 락을 보유한 상태에서 실행
- `_execute_once(self, thread_ts, prompt, msg_ts)` (줄 282): 단일 Claude 실행 -- Soulstream 서버에 위임
- `_get_role_config(self, role)` (줄 327): 역할에 맞는 runner 설정을 반환 (모듈 함수에 위임)
- `_get_service_adapter(self)` (줄 331): Remote 모드용 ClaudeServiceAdapter를 생성하여 반환 (호출마다 새 인스턴스)
- `_register_session_id(self, thread_ts, session_id)` (줄 350): thread_ts <-> agent_session_id 매핑 등록 및 버퍼된 인터벤션 flush
- `_unregister_session_id(self, thread_ts)` (줄 374): thread_ts <-> agent_session_id 매핑 해제
- `get_session_id(self, thread_ts)` (줄 383): thread_ts에 대응하는 agent_session_id 조회
- `_execute_remote(self, thread_ts, prompt)` (줄 388): Remote 모드: Soulstream 서버에 실행을 위임 (per-session)
- `_process_result(self, presentation, result, thread_ts)` (줄 475): 실행 결과 처리

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

- `seosoyoung.slackbot.soulstream.engine_types.ClaudeResult`
- `seosoyoung.slackbot.soulstream.engine_types.CompactCallback`
- `seosoyoung.slackbot.soulstream.intervention.InterventionManager`
- `seosoyoung.slackbot.soulstream.result_processor.ResultProcessor`
- `seosoyoung.slackbot.soulstream.session.SessionManager`
- `seosoyoung.slackbot.soulstream.session.SessionRuntime`
- `seosoyoung.slackbot.soulstream.types.UpdateMessageFn`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
