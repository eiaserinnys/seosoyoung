# claude/executor.py

> 경로: `seosoyoung/slackbot/claude/executor.py`

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
- 위치: 줄 70
- 설명: 실행 컨텍스트 - 메서드 간 전달되는 모든 실행 상태를 묶는 객체

executor 내부 메서드들이 공유하는 상태를 하나의 객체로 캡슐화합니다.

#### 메서드

- `original_thread_ts(self)` (줄 103): 세션의 원래 thread_ts

### `ClaudeExecutor`
- 위치: 줄 108
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, send_long_message, send_restart_confirmation, trello_watcher_ref, list_runner_ref)` (줄 115): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 158): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, ctx, prompt)` (줄 228): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_run_with_lock(self, ctx, prompt)` (줄 260): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, ctx, prompt)` (줄 299): 단일 Claude 실행
- `_get_service_adapter(self)` (줄 405): Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환
- `_execute_remote(self, ctx, prompt)` (줄 422): Remote 모드: soul 서버에 실행을 위임
- `_process_result(self, ctx, result)` (줄 452): 실행 결과 처리
- `_replace_thinking_message(self)` (줄 474): 하위 호환: ResultProcessor에 위임
- `_handle_interrupted(self, ctx)` (줄 478): 하위 호환: ResultProcessor에 위임
- `_handle_success(self, ctx, result)` (줄 482): 하위 호환: ResultProcessor에 위임
- `_handle_trello_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 486): 하위 호환: ResultProcessor에 위임
- `_handle_normal_success(self, ctx, result, response, is_list_run, usage_bar)` (줄 490): 하위 호환: ResultProcessor에 위임
- `_handle_restart_marker(self, result, session, channel, thread_ts, say)` (줄 494): 하위 호환: ResultProcessor에 위임
- `_handle_list_run_marker(self, list_name, channel, thread_ts, say, client)` (줄 498): 하위 호환: ResultProcessor에 위임
- `_handle_error(self, ctx, error)` (줄 502): 하위 호환: ResultProcessor에 위임
- `_handle_exception(self, ctx, e)` (줄 506): 하위 호환: ResultProcessor에 위임

## 함수

### `_is_remote_mode()`
- 위치: 줄 37
- 설명: 현재 실행 모드가 remote인지 확인

### `_get_mcp_config_path()`
- 위치: 줄 42
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

### `_get_role_config(role)`
- 위치: 줄 48
- 설명: 역할에 맞는 runner 설정을 반환

Returns:
    dict with keys: allowed_tools, disallowed_tools, mcp_config_path

## 내부 의존성

- `seosoyoung.slackbot.claude.agent_runner.ClaudeRunner`
- `seosoyoung.slackbot.claude.intervention.InterventionManager`
- `seosoyoung.slackbot.claude.intervention.PendingPrompt`
- `seosoyoung.slackbot.claude.message_formatter.format_as_blockquote`
- `seosoyoung.slackbot.claude.message_formatter.format_dm_progress`
- `seosoyoung.slackbot.claude.message_formatter.format_trello_progress`
- `seosoyoung.slackbot.claude.message_formatter.truncate_progress_text`
- `seosoyoung.slackbot.claude.result_processor.ResultProcessor`
- `seosoyoung.slackbot.claude.session.Session`
- `seosoyoung.slackbot.claude.session.SessionManager`
- `seosoyoung.slackbot.claude.types.CardInfo`
- `seosoyoung.slackbot.claude.types.CompactCallback`
- `seosoyoung.slackbot.claude.types.ProgressCallback`
- `seosoyoung.slackbot.claude.types.SayFunction`
- `seosoyoung.slackbot.claude.types.SlackClient`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.slack.formatting.update_message`
