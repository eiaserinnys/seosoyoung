# claude/executor.py

> 경로: `seosoyoung/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.
인터벤션(intervention) 기능을 지원하여, 실행 중 새 메시지가 도착하면
현재 실행을 중단하고 새 프롬프트로 이어서 실행합니다.

## 클래스

### `PendingPrompt`
- 위치: 줄 61
- 설명: 인터벤션 대기 중인 프롬프트 정보

### `ClaudeExecutor`
- 위치: 줄 76
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, upload_file_to_slack, send_long_message, send_restart_confirmation, trello_watcher_ref, list_runner_ref)` (줄 83): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts)` (줄 116): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, thread_ts, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts)` (줄 179): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_pop_pending(self, thread_ts)` (줄 232): pending 프롬프트를 꺼내고 제거
- `_run_with_lock(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts)` (줄 237): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, session, prompt, msg_ts, channel, say, client, effective_role, trello_card, is_existing_thread, initial_msg_ts, is_trello_mode, thread_ts_override, dm_channel_id, dm_thread_ts)` (줄 308): 단일 Claude 실행
- `_is_last_message(self, client, channel, msg_ts, thread_ts)` (줄 569): 사고 과정 메시지가 채널/스레드에서 마지막 메시지인지 확인
- `_replace_thinking_message(self, client, channel, old_msg_ts, new_text, new_blocks, thread_ts)` (줄 608): 사고 과정 메시지를 삭제하고 새 메시지로 교체
- `_handle_interrupted(self, last_msg_ts, main_msg_ts, is_trello_mode, trello_card, session, channel, client, dm_channel_id, dm_last_reply_ts)` (줄 669): 인터럽트로 중단된 실행의 사고 과정 메시지 정리
- `_handle_success(self, result, session, effective_role, is_trello_mode, trello_card, channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_thread_ts, dm_last_reply_ts)` (줄 715): 성공 결과 처리
- `_handle_trello_success(self, result, response, session, trello_card, channel, thread_ts, main_msg_ts, say, client, is_list_run, usage_bar, dm_channel_id, dm_thread_ts, dm_last_reply_ts)` (줄 779): 트렐로 모드 성공 처리
- `_handle_normal_success(self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client, is_thread_reply, is_list_run, usage_bar)` (줄 892): 일반 모드(멘션) 성공 처리
- `_handle_restart_marker(self, result, session, thread_ts, say)` (줄 1000): 재기동 마커 처리
- `_handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 1023): LIST_RUN 마커 처리 - 정주행 시작
- `_handle_error(self, error, is_trello_mode, trello_card, session, channel, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_last_reply_ts)` (줄 1092): 오류 결과 처리
- `_handle_exception(self, e, is_trello_mode, trello_card, session, channel, thread_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply, dm_channel_id, dm_last_reply_ts)` (줄 1148): 예외 처리

## 함수

### `_get_mcp_config_path()`
- 위치: 줄 39
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

### `get_runner_for_role(role)`
- 위치: 줄 45
- 설명: 역할에 맞는 ClaudeAgentRunner 반환

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.claude.message_formatter.build_context_usage_bar`
- `seosoyoung.claude.message_formatter.build_trello_header`
- `seosoyoung.claude.message_formatter.escape_backticks`
- `seosoyoung.claude.message_formatter.parse_summary_details`
- `seosoyoung.claude.message_formatter.strip_summary_details_markers`
- `seosoyoung.claude.reaction_manager.INTERVENTION_ACCEPTED_EMOJI`
- `seosoyoung.claude.reaction_manager.INTERVENTION_EMOJI`
- `seosoyoung.claude.reaction_manager.TRELLO_REACTIONS`
- `seosoyoung.claude.reaction_manager.add_reaction`
- `seosoyoung.claude.reaction_manager.remove_reaction`
- `seosoyoung.claude.session.Session`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.trello.watcher.TrackedCard`
