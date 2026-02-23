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

### `PendingPrompt`
- 위치: 줄 69
- 설명: 인터벤션 대기 중인 프롬프트 정보

### `ClaudeExecutor`
- 위치: 줄 85
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, upload_file_to_slack, send_long_message, send_restart_confirmation, trello_watcher_ref, list_runner_ref)` (줄 92): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 131): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, thread_ts, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 198): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_pop_pending(self, thread_ts)` (줄 270): pending 프롬프트를 꺼내고 제거
- `_run_with_lock(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 275): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, session, prompt, msg_ts, channel, say, client, effective_role, trello_card, is_existing_thread, initial_msg_ts, is_trello_mode, thread_ts_override, dm_channel_id, dm_thread_ts, user_message)` (줄 345): 단일 Claude 실행
- `_get_service_adapter(self)` (줄 547): Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환
- `_execute_remote(self, session, prompt, thread_ts, original_thread_ts, on_progress, on_compact, last_msg_ts, main_msg_ts, msg_ts, is_trello_mode, trello_card, effective_role, is_thread_reply, channel, say, client, dm_channel_id, dm_thread_ts, dm_last_reply_ts, user_message)` (줄 564): Remote 모드: soul 서버에 실행을 위임
- `_process_result(self, result, session, effective_role, is_trello_mode, trello_card, channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_thread_ts, dm_last_reply_ts)` (줄 628): 실행 결과 처리 (local/remote 공통)
- `_replace_thinking_message(self, client, channel, old_msg_ts, new_text, new_blocks, thread_ts)` (줄 680): 사고 과정 메시지를 최종 응답으로 교체 (chat_update)
- `_handle_interrupted(self, last_msg_ts, main_msg_ts, is_trello_mode, trello_card, session, channel, client, dm_channel_id, dm_last_reply_ts)` (줄 705): 인터럽트로 중단된 실행의 사고 과정 메시지 정리
- `_handle_success(self, result, session, effective_role, is_trello_mode, trello_card, channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_thread_ts, dm_last_reply_ts)` (줄 751): 성공 결과 처리
- `_handle_trello_success(self, result, response, session, trello_card, channel, thread_ts, main_msg_ts, say, client, is_list_run, usage_bar, dm_channel_id, dm_thread_ts, dm_last_reply_ts)` (줄 815): 트렐로 모드 성공 처리
- `_handle_normal_success(self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client, is_thread_reply, is_list_run, usage_bar)` (줄 877): 일반 모드(멘션) 성공 처리
- `_handle_restart_marker(self, result, session, channel, thread_ts, say)` (줄 964): 재기동 마커 처리
- `_handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 987): LIST_RUN 마커 처리 - 정주행 시작
- `_handle_error(self, error, is_trello_mode, trello_card, session, channel, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_last_reply_ts)` (줄 1056): 오류 결과 처리
- `_handle_exception(self, e, is_trello_mode, trello_card, session, channel, msg_ts, thread_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_last_reply_ts)` (줄 1107): 예외 처리

## 함수

### `_is_remote_mode()`
- 위치: 줄 34
- 설명: 현재 실행 모드가 remote인지 확인

### `_get_mcp_config_path()`
- 위치: 줄 39
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

### `get_runner_for_role(role)`
- 위치: 줄 45
- 설명: 역할에 맞는 ClaudeAgentRunner 반환 (캐시된 인스턴스)

동일한 role에 대해서는 항상 같은 ClaudeAgentRunner 인스턴스를 반환합니다.
이를 통해 클래스 레벨의 _active_clients 관리가 일관되게 유지됩니다.

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.claude.message_formatter.build_context_usage_bar`
- `seosoyoung.claude.message_formatter.build_trello_header`
- `seosoyoung.claude.message_formatter.escape_backticks`
- `seosoyoung.claude.session.Session`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.trello.watcher.TrackedCard`
