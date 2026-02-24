# claude/agent_runner.py

> 경로: `seosoyoung/slackbot/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 51
- 설명: Claude Code 실행 결과

### `CompactRetryState`
- 위치: 줄 151
- 설명: Compact retry 외부 루프 상태

#### 메서드

- `snapshot(self)` (줄 157): 현재 이벤트 수 기록 (외부 루프 시작 시 호출)
- `did_compact(self, before)` (줄 161): 스냅샷 이후 compact가 발생했는지
- `can_retry(self)` (줄 165): 
- `increment(self)` (줄 168): 

### `MessageState`
- 위치: 줄 173
- 설명: 메시지 수신 루프 상태

#### 메서드

- `has_result(self)` (줄 186): 
- `reset_for_retry(self)` (줄 189): compact retry 시 텍스트 상태 리셋

### `ClaudeRunner`
- 위치: 줄 204
- 설명: Claude Code SDK 기반 실행기

thread_ts 단위 인스턴스: 각 인스턴스가 자신의 client/pid/execution_loop를 소유합니다.

#### 메서드

- `__init__(self, thread_ts)` (줄 210): 
- `async shutdown_all_clients(cls)` (줄 241): 하위 호환: 모듈 레벨 shutdown_all()로 위임
- `shutdown_all_clients_sync(cls)` (줄 246): 하위 호환: 모듈 레벨 shutdown_all_sync()로 위임
- `run_sync(self, coro)` (줄 250): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `async _get_or_create_client(self, options)` (줄 254): ClaudeSDKClient를 가져오거나 새로 생성
- `async _remove_client(self)` (줄 299): 이 러너의 ClaudeSDKClient를 정리
- `_force_kill_process(pid, thread_ts)` (줄 318): psutil을 사용하여 프로세스를 강제 종료
- `_is_cli_alive(self)` (줄 335): CLI 서브프로세스가 아직 살아있는지 확인
- `interrupt(self)` (줄 345): 이 러너에 인터럽트 전송 (동기)
- `_build_compact_hook(self, compact_events)` (줄 360): PreCompact 훅을 생성합니다.
- `_build_options(self, session_id, compact_events, user_id, prompt)` (줄 397): ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts, stderr 파일을 반환합니다.
- `async _notify_compact_events(self, compact_state, on_compact)` (줄 464): 미통지 compact 이벤트를 on_compact 콜백으로 전달
- `async _receive_messages(self, client, compact_state, msg_state, on_progress, on_compact)` (줄 482): 내부 메시지 수신 루프: receive_response()에서 메시지를 읽어 상태 갱신
- `_evaluate_compact_retry(self, compact_state, msg_state, before_snapshot)` (줄 620): Compact retry 판정. True이면 외부 루프 continue, False이면 break.
- `async run(self, prompt, session_id, on_progress, on_compact, user_id, user_message)` (줄 680): Claude Code 실행
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id)` (줄 700): 실제 실행 로직 (ClaudeSDKClient 기반)
- `async compact_session(self, session_id)` (줄 887): 세션 컴팩트 처리

## 함수

### `get_runner(thread_ts)`
- 위치: 줄 74
- 설명: 레지스트리에서 러너 조회

### `register_runner(runner)`
- 위치: 줄 80
- 설명: 레지스트리에 러너 등록

### `remove_runner(thread_ts)`
- 위치: 줄 86
- 설명: 레지스트리에서 러너 제거

### `async shutdown_all()`
- 위치: 줄 92
- 설명: 모든 등록된 러너의 클라이언트를 종료

프로세스 종료 전에 호출하여 고아 프로세스를 방지합니다.

Returns:
    종료된 클라이언트 수

### `shutdown_all_sync()`
- 위치: 줄 127
- 설명: 모든 등록된 러너의 클라이언트를 종료 (동기 버전)

시그널 핸들러 등 동기 컨텍스트에서 사용합니다.

Returns:
    종료된 클라이언트 수

### `_extract_last_assistant_text(collected_messages)`
- 위치: 줄 196
- 설명: collected_messages에서 마지막 assistant 텍스트를 추출 (tool_use 제외)

### `async main()`
- 위치: 줄 909

## 내부 의존성

- `seosoyoung.slackbot.claude.diagnostics.DebugSendFn`
- `seosoyoung.slackbot.claude.diagnostics.build_session_dump`
- `seosoyoung.slackbot.claude.diagnostics.classify_process_error`
- `seosoyoung.slackbot.claude.diagnostics.format_rate_limit_warning`
- `seosoyoung.slackbot.claude.diagnostics.send_debug_to_slack`
- `seosoyoung.slackbot.claude.types.OnCompactOMFlagFn`
- `seosoyoung.slackbot.claude.types.PrepareMemoryFn`
- `seosoyoung.slackbot.claude.types.TriggerObservationFn`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
