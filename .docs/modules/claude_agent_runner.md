# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 178
- 설명: Claude Code 실행 결과

### `ClaudeAgentRunner`
- 위치: 줄 217
- 설명: Claude Code SDK 기반 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools, mcp_config_path)` (줄 226): 
- `async shutdown_all_clients(cls)` (줄 243): 모든 활성 클라이언트 종료
- `shutdown_all_clients_sync(cls)` (줄 282): 모든 활성 클라이언트 종료 (동기 버전)
- `run_sync(self, coro)` (줄 299): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `async _get_or_create_client(self, thread_ts, options)` (줄 307): 스레드에 대한 ClaudeSDKClient를 가져오거나 새로 생성
- `async _remove_client(self, thread_ts)` (줄 362): 스레드의 ClaudeSDKClient를 정리
- `_force_kill_process(pid, thread_ts)` (줄 385): psutil을 사용하여 프로세스를 강제 종료
- `interrupt(self, thread_ts)` (줄 408): 실행 중인 스레드에 인터럽트 전송 (동기)
- `_build_options(self, session_id, compact_events, user_id, thread_ts, channel, prompt)` (줄 431): ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts를 함께 반환합니다.
- `_send_injection_debug_log(thread_ts, result, debug_channel, anchor_ts)` (줄 619): 디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송
- `async run(self, prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel, user_message)` (줄 702): Claude Code 실행
- `_trigger_observation(self, thread_ts, user_id, prompt, collected_messages, anchor_ts)` (줄 736): 관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel)` (줄 829): 실제 실행 로직 (ClaudeSDKClient 기반)
- `async compact_session(self, session_id)` (줄 1212): 세션 컴팩트 처리

## 함수

### `_get_slack_client()`
- 위치: 줄 34
- 설명: 슬랙 클라이언트 가져오기 (lazy init)

### `_send_debug_to_slack(channel, thread_ts, message)`
- 위치: 줄 44
- 설명: 슬랙에 디버그 메시지 전송 (별도 메시지로)

### `_read_stderr_tail(n_lines)`
- 위치: 줄 58
- 설명: cli_stderr.log의 마지막 N줄 읽기

### `_build_session_dump()`
- 위치: 줄 73
- 설명: 세션 종료 진단 덤프 메시지 생성

### `_classify_process_error(e)`
- 위치: 줄 113
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.

### `run_in_new_loop(coro)`
- 위치: 줄 193
- 설명: 별도 스레드에서 새 이벤트 루프로 코루틴을 실행 (블로킹)

각 호출마다 격리된 이벤트 루프를 생성하여
이전 실행의 anyio 잔여물이 영향을 미치지 않도록 합니다.

### `async main()`
- 위치: 줄 1242
