# claude/agent_runner.py

> 경로: `seosoyoung/slackbot/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 51
- 설명: Claude Code 실행 결과

### `ClaudeRunner`
- 위치: 줄 148
- 설명: Claude Code SDK 기반 실행기

thread_ts 단위 인스턴스: 각 인스턴스가 자신의 client/pid/execution_loop를 소유합니다.

#### 메서드

- `__init__(self, thread_ts)` (줄 154): 
- `async shutdown_all_clients(cls)` (줄 179): 하위 호환: 모듈 레벨 shutdown_all()로 위임
- `shutdown_all_clients_sync(cls)` (줄 184): 하위 호환: 모듈 레벨 shutdown_all_sync()로 위임
- `run_sync(self, coro)` (줄 188): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `async _get_or_create_client(self, options)` (줄 192): ClaudeSDKClient를 가져오거나 새로 생성
- `async _remove_client(self)` (줄 237): 이 러너의 ClaudeSDKClient를 정리
- `_force_kill_process(pid, thread_ts)` (줄 256): psutil을 사용하여 프로세스를 강제 종료
- `interrupt(self)` (줄 273): 이 러너에 인터럽트 전송 (동기)
- `_build_compact_hook(self, compact_events)` (줄 288): PreCompact 훅을 생성합니다.
- `_build_options(self, session_id, compact_events, user_id, prompt)` (줄 332): ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts, stderr 파일을 반환합니다.
- `async run(self, prompt, session_id, on_progress, on_compact, user_id, user_message)` (줄 396): Claude Code 실행
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id)` (줄 416): 실제 실행 로직 (ClaudeSDKClient 기반)
- `async compact_session(self, session_id)` (줄 743): 세션 컴팩트 처리

## 함수

### `get_runner(thread_ts)`
- 위치: 줄 73
- 설명: 레지스트리에서 러너 조회

### `register_runner(runner)`
- 위치: 줄 79
- 설명: 레지스트리에 러너 등록

### `remove_runner(thread_ts)`
- 위치: 줄 85
- 설명: 레지스트리에서 러너 제거

### `async shutdown_all()`
- 위치: 줄 91
- 설명: 모든 등록된 러너의 클라이언트를 종료

프로세스 종료 전에 호출하여 고아 프로세스를 방지합니다.

Returns:
    종료된 클라이언트 수

### `shutdown_all_sync()`
- 위치: 줄 126
- 설명: 모든 등록된 러너의 클라이언트를 종료 (동기 버전)

시그널 핸들러 등 동기 컨텍스트에서 사용합니다.

Returns:
    종료된 클라이언트 수

### `async main()`
- 위치: 줄 768

## 내부 의존성

- `seosoyoung.slackbot.claude.diagnostics.build_session_dump`
- `seosoyoung.slackbot.claude.diagnostics.classify_process_error`
- `seosoyoung.slackbot.claude.diagnostics.format_rate_limit_warning`
- `seosoyoung.slackbot.claude.diagnostics.send_debug_to_slack`
- `seosoyoung.slackbot.memory.injector.create_or_load_debug_anchor`
- `seosoyoung.slackbot.memory.injector.prepare_memory_injection`
- `seosoyoung.slackbot.memory.injector.send_injection_debug_log`
- `seosoyoung.slackbot.memory.injector.trigger_observation`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
