# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 94
- 설명: Claude Code 실행 결과

### `ClaudeAgentRunner`
- 위치: 줄 109
- 설명: Claude Code SDK 기반 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools, mcp_config_path)` (줄 117): 
- `_ensure_loop(cls)` (줄 134): 공유 이벤트 루프가 없거나 닫혀있으면 데몬 스레드에서 새로 생성
- `_reset_shared_loop(cls)` (줄 153): 공유 루프를 리셋 (테스트용)
- `run_sync(self, coro)` (줄 163): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `async _get_or_create_client(self, thread_ts, options)` (줄 173): 스레드에 대한 ClaudeSDKClient를 가져오거나 새로 생성
- `async _remove_client(self, thread_ts)` (줄 210): 스레드의 ClaudeSDKClient를 정리
- `async interrupt(self, thread_ts)` (줄 225): 실행 중인 스레드에 인터럽트 전송
- `_build_options(self, session_id, compact_events, user_id, thread_ts, channel, prompt)` (줄 245): ClaudeCodeOptions, OM 메모리 프롬프트, 디버그 앵커 ts를 함께 반환합니다.
- `_send_injection_debug_log(thread_ts, result, debug_channel, anchor_ts)` (줄 433): 디버그 이벤트 #7, #8: 주입 정보를 슬랙에 발송
- `async run(self, prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel, user_message)` (줄 516): Claude Code 실행
- `_trigger_observation(self, thread_ts, user_id, prompt, collected_messages, anchor_ts)` (줄 550): 관찰 파이프라인을 별도 스레드에서 비동기로 트리거 (봇 응답 블로킹 없음)
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id, thread_ts, channel)` (줄 643): 실제 실행 로직 (ClaudeSDKClient 기반)
- `async compact_session(self, session_id)` (줄 916): 세션 컴팩트 처리

## 함수

### `_classify_process_error(e)`
- 위치: 줄 29
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.

### `async main()`
- 위치: 줄 946
