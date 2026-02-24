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

### `ExecutionContext`
- 위치: 줄 54
- 설명: 실행 컨텍스트 - 메서드 간 전달되는 모든 실행 상태를 묶는 객체

executor 내부 메서드들이 공유하는 상태를 하나의 객체로 캡슐화합니다.

#### 메서드

- `original_thread_ts(self)` (줄 87): 세션의 원래 thread_ts

### `ClaudeExecutor`
- 위치: 줄 92
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.
인터벤션 기능을 지원합니다.

#### 메서드

- `__init__(self, session_manager, session_runtime, restart_manager, send_long_message, send_restart_confirmation, update_message_fn)` (줄 99): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread, initial_msg_ts, dm_channel_id, dm_thread_ts, user_message)` (줄 162): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_intervention(self, ctx, prompt)` (줄 232): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_run_with_lock(self, ctx, prompt)` (줄 264): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, ctx, prompt)` (줄 303): 단일 Claude 실행
- `_get_role_config(self, role)` (줄 378): 역할에 맞는 runner 설정을 반환
- `_get_service_adapter(self)` (줄 398): Remote 모드용 ClaudeServiceAdapter를 lazy 초기화하여 반환
- `_execute_remote(self, ctx, prompt)` (줄 415): Remote 모드: soul 서버에 실행을 위임
- `async _on_progress(self, ctx, current_text)` (줄 443): 사고 과정 메시지 업데이트 콜백
- `async _on_compact(self, ctx, trigger, message)` (줄 470): 컨텍스트 압축 알림 콜백
- `_process_result(self, ctx, result)` (줄 479): 실행 결과 처리

## 함수

### `_get_runtime_dir()`
- 위치: 줄 39
- 설명: 런타임 디렉토리 반환 (SEOSOYOUNG_RUNTIME 환경변수 우선, 폴백: __file__ 기준)

### `_get_mcp_config_path()`
- 위치: 줄 47
- 설명: MCP 설정 파일 경로 반환 (없으면 None)

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
- `seosoyoung.slackbot.claude.session.SessionRuntime`
- `seosoyoung.slackbot.claude.types.CardInfo`
- `seosoyoung.slackbot.claude.types.CompactCallback`
- `seosoyoung.slackbot.claude.types.OnCompactOMFlagFn`
- `seosoyoung.slackbot.claude.types.PrepareMemoryFn`
- `seosoyoung.slackbot.claude.types.ProgressCallback`
- `seosoyoung.slackbot.claude.types.SayFunction`
- `seosoyoung.slackbot.claude.types.SlackClient`
- `seosoyoung.slackbot.claude.types.TriggerObservationFn`
- `seosoyoung.slackbot.claude.types.UpdateMessageFn`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
