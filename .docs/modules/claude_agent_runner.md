# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 202
- 설명: Claude Code 실행 결과

### `ClaudeRunner`
- 위치: 줄 319
- 설명: Claude Code SDK 기반 실행기

thread_ts 단위 인스턴스: 각 인스턴스가 자신의 client/pid/execution_loop를 소유합니다.

#### 메서드

- `__init__(self, thread_ts)` (줄 325): 
- `async shutdown_all_clients(cls)` (줄 349): 하위 호환: 모듈 레벨 shutdown_all()로 위임
- `shutdown_all_clients_sync(cls)` (줄 354): 하위 호환: 모듈 레벨 shutdown_all_sync()로 위임
- `run_sync(self, coro)` (줄 358): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `async _get_or_create_client(self, options)` (줄 366): ClaudeSDKClient를 가져오거나 새로 생성
- `async _remove_client(self)` (줄 416): 이 러너의 ClaudeSDKClient를 정리
- `_force_kill_process(pid, thread_ts)` (줄 439): psutil을 사용하여 프로세스를 강제 종료
- `interrupt(self)` (줄 462): 이 러너에 인터럽트 전송 (동기)
- `_build_compact_hook(self, compact_events)` (줄 481): PreCompact 훅을 생성합니다.
- `_create_or_load_debug_anchor(self, thread_ts, session_id, store, prompt, debug_channel)` (줄 532): 디버그 앵커 메시지를 생성하거나 기존 앵커를 로드합니다.
- `_prepare_memory_injection(self, session_id, prompt)` (줄 588): OM 메모리 주입을 준비합니다.
- `_build_options(self, session_id, compact_events, user_id, prompt)` (줄 672): ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts, stderr 파일을 반환합니다.
- `_send_injection_debug_log(thread_ts, result, debug_channel, anchor_ts)` (줄 742): 디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송
- `async run(self, prompt, session_id, on_progress, on_compact, user_id, user_message)` (줄 825): Claude Code 실행
- `_trigger_observation(self, thread_ts, user_id, prompt, collected_messages, anchor_ts)` (줄 855): 관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id)` (줄 948): 실제 실행 로직 (ClaudeSDKClient 기반)
- `async compact_session(self, session_id)` (줄 1247): 세션 컴팩트 처리

## 함수

### `_get_slack_client()`
- 위치: 줄 34
- 설명: 슬랙 클라이언트 가져오기 (lazy init)

### `_send_debug_to_slack(channel, thread_ts, message)`
- 위치: 줄 44
- 설명: 슬랙에 디버그 메시지 전송 (별도 메시지로)

### `_read_stderr_tail(n_lines)`
- 위치: 줄 58
- 설명: 세션별 cli_stderr 로그의 마지막 N줄 읽기

세션별 파일(cli_stderr_{thread_ts}.log)을 우선 시도하고,
없으면 공유 파일(cli_stderr.log)로 폴백합니다.

Args:
    n_lines: 읽을 줄 수
    thread_ts: 스레드 타임스탬프 (None이면 "default" 사용)

### `_build_session_dump()`
- 위치: 줄 92
- 설명: 세션 종료 진단 덤프 메시지 생성

Args:
    thread_ts: 스레드 타임스탬프 (세션별 stderr 파일 식별용)

### `_classify_process_error(e)`
- 위치: 줄 137
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.

### `run_in_new_loop(coro)`
- 위치: 줄 217
- 설명: 별도 스레드에서 새 이벤트 루프로 코루틴을 실행 (블로킹)

각 호출마다 격리된 이벤트 루프를 생성하여
이전 실행의 anyio 잔여물이 영향을 미치지 않도록 합니다.

### `get_runner(thread_ts)`
- 위치: 줄 248
- 설명: 레지스트리에서 러너 조회

### `register_runner(runner)`
- 위치: 줄 254
- 설명: 레지스트리에 러너 등록

### `remove_runner(thread_ts)`
- 위치: 줄 260
- 설명: 레지스트리에서 러너 제거

### `async shutdown_all()`
- 위치: 줄 266
- 설명: 모든 등록된 러너의 클라이언트를 종료

프로세스 종료 전에 호출하여 고아 프로세스를 방지합니다.

Returns:
    종료된 클라이언트 수

### `shutdown_all_sync()`
- 위치: 줄 301
- 설명: 모든 등록된 러너의 클라이언트를 종료 (동기 버전)

시그널 핸들러 등 동기 컨텍스트에서 사용합니다.

Returns:
    종료된 클라이언트 수

### `async main()`
- 위치: 줄 1281
