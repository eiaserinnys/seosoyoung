# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 ClaudeAgentRunner에서 핵심 로직을 복제한 경량 버전:
- _classify_process_error: ProcessError를 사용자 친화적 메시지로 변환
- _build_options: ClaudeCodeOptions 생성 (OM, hooks, compact 제외)
- _get_or_create_client / _remove_client: 클라이언트 생명주기 관리
- _execute: 실제 실행 로직 (메인 봇과 동일한 구조)
- run / run_sync: async/sync 인터페이스

## 클래스

### `RescueResult`
- 위치: 줄 79
- 설명: 실행 결과

### `RescueRunner`
- 위치: 줄 88
- 설명: Claude Code SDK 실행기 (공유 이벤트 루프 기반)

메인 봇의 ClaudeAgentRunner와 동일한 패턴:
- 클래스 레벨 공유 이벤트 루프 (데몬 스레드)
- run_coroutine_threadsafe로 동기→비동기 브릿지
- _get_or_create_client / _remove_client로 클라이언트 생명주기 관리

#### 메서드

- `__init__(self)` (줄 102): 
- `_ensure_loop(cls)` (줄 107): 공유 이벤트 루프가 없거나 닫혀있으면 데몬 스레드에서 새로 생성
- `_reset_shared_loop(cls)` (줄 126): 공유 루프를 리셋 (테스트용)
- `run_sync(self, coro)` (줄 136): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `run_claude_sync(self, prompt, session_id, thread_ts)` (줄 146): 동기 컨텍스트에서 Claude Code SDK를 호출합니다.
- `_build_options(self, session_id)` (줄 158): ClaudeCodeOptions를 생성합니다.
- `async _get_or_create_client(self, client_key, options)` (줄 194): 클라이언트를 가져오거나 새로 생성 (메인 봇 동일 패턴)
- `async _remove_client(self, client_key)` (줄 224): 클라이언트를 정리 (메인 봇 동일 패턴)
- `async run(self, prompt, session_id, thread_ts)` (줄 238): Claude Code 실행 (async, lock 포함)
- `async _execute(self, prompt, session_id, thread_ts)` (줄 251): 실제 실행 로직 (메인 봇 _execute와 동일한 구조)

## 함수

### `_classify_process_error(e)`
- 위치: 줄 51
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

메인 봇의 _classify_process_error와 동일한 로직입니다.

### `run_claude_sync(prompt, session_id, thread_ts)`
- 위치: 줄 376
- 설명: 모듈 레벨 래퍼 — main.py 호환용

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
