# claude/executor.py

> 경로: `seosoyoung/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

실행 모드 (CLAUDE_EXECUTION_MODE):
- local: 기존 방식. ClaudeAgentRunner를 직접 사용하여 로컬에서 실행.
- remote: seosoyoung-soul 서버에 HTTP/SSE로 위임하여 실행.

## 클래스

### `ExecutionContext`
- 위치: 줄 67
- 설명: 실행 컨텍스트 - 메서드 간 전달되는 모든 실행 상태를 묶는 객체

executor 내부 메서드들이 공유하는 상태를 하나의 객체로 캡슐화합니다.

#### 메서드

- `original_thread_ts(self)` (줄 100): 세션의 원래 thread_ts

### `PendingPrompt`
- 위치: 줄 106
- 설명: 인터벤션 대기 중인 프롬프트 정보

### `ClaudeExecutor`
- 위치: 줄 122
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, upload_file_to_slack, send_long_message, send_restart_confirmation, trello_watcher_ref, list_runner_ref)` (줄 129): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 164): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, ctx, prompt)` (줄 234): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_pop_pending(self, thread_ts)` (줄 291): pending 프롬프트를 꺼내고 제거
- `_run_with_lock(self, ctx, prompt)` (줄 296): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, ctx, prompt)` (줄 335): 단일 Claude 실행
- `_get_service_adapter(self)` (줄 483): Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환
- `_execute_remote(self, ctx, prompt)` (줄 500): Remote 모드: soul 서버에 실행을 위임
- `_process_result(self, ctx, result)` (줄 530): 실행 결과 처리 (local/remote 공통)
- `_replace_thinking_message(self, client, channel, old_msg_ts, new_text, new_blocks, thread_ts)` (줄 548): 사고 과정 메시지를 최종 응답으로 교체 (chat_update)
- `_handle_interrupted(self, ctx)` (줄 573): 인터럽트로 중단된 실행의 사고 과정 메시지 정리
- `_handle_success(self, ctx, result)` (줄 614): 성공 결과 처리
- `_handle_trello_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 652): 트렐로 모드 성공 처리
- `_handle_normal_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 707): 일반 모드(멘션) 성공 처리
- `_handle_restart_marker(self, result, session, channel, thread_ts, say)` (줄 787): 재기동 마커 처리
- `_handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 810): LIST_RUN 마커 처리 - 정주행 시작
- `_handle_error(self, ctx, error)` (줄 879): 오류 결과 처리
- `_handle_exception(self, ctx, e)` (줄 923): 예외 처리

## 함수

### `_is_remote_mode()`
- 위치: 줄 34
- 설명: 현재 실행 모드가 remote인지 확인

### `_get_mcp_config_path()`
- 위치: 줄 39
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

### `_get_role_config(role)`
- 위치: 줄 45
- 설명: 역할에 맞는 runner 설정을 반환

Returns:
    dict with keys: allowed_tools, disallowed_tools, mcp_config_path

## 내부 의존성

- `seosoyoung.claude.agent_runner.ClaudeRunner`
- `seosoyoung.claude.agent_runner.get_runner`
- `seosoyoung.claude.message_formatter.build_context_usage_bar`
- `seosoyoung.claude.message_formatter.build_trello_header`
- `seosoyoung.claude.message_formatter.escape_backticks`
- `seosoyoung.claude.session.Session`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.trello.watcher.TrackedCard`
