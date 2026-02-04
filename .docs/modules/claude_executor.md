# claude/executor.py

> 경로: `seosoyoung/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.

## 클래스

### `ClaudeExecutor`
- 위치: 줄 42
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, upload_file_to_slack, send_long_message, send_restart_confirmation)` (줄 48): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts)` (줄 70): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_success(self, result, session, effective_role, is_trello_mode, trello_card, channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 269): 성공 결과 처리
- `_handle_trello_success(self, result, response, session, trello_card, channel, thread_ts, main_msg_ts, say, client)` (줄 301): 트렐로 모드 성공 처리
- `_handle_normal_success(self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client, is_thread_reply)` (줄 382): 일반 모드(멘션) 성공 처리
- `_handle_restart_marker(self, result, session, thread_ts, say)` (줄 473): 재기동 마커 처리
- `_handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 496): LIST_RUN 마커 처리 - 정주행 스레드 생성
- `_handle_error(self, error, is_trello_mode, trello_card, session, channel, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 538): 오류 결과 처리
- `_handle_exception(self, e, is_trello_mode, trello_card, session, channel, thread_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 581): 예외 처리

## 함수

### `get_runner_for_role(role)`
- 위치: 줄 30
- 설명: 역할에 맞는 ClaudeAgentRunner 반환

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.claude.message_formatter.build_trello_header`
- `seosoyoung.claude.message_formatter.escape_backticks`
- `seosoyoung.claude.message_formatter.parse_summary_details`
- `seosoyoung.claude.message_formatter.strip_summary_details_markers`
- `seosoyoung.claude.reaction_manager.TRELLO_REACTIONS`
- `seosoyoung.claude.reaction_manager.add_reaction`
- `seosoyoung.claude.reaction_manager.remove_reaction`
- `seosoyoung.claude.session.Session`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.trello.watcher.TrackedCard`
