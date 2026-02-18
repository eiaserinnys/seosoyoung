# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 ClaudeAgentRunner와 동일한 패턴을 사용합니다:
- 클래스 레벨 공유 이벤트 루프 (데몬 스레드)
- _get_or_create_client / _remove_client로 클라이언트 생명주기 관리
- finally에서 _remove_client로 disconnect (transport 내부 접근 없음)

## 클래스

### `RescueResult`
- 위치: 줄 50
- 설명: 실행 결과

### `RescueRunner`
- 위치: 줄 59
- 설명: Claude Code SDK 실행기 (공유 이벤트 루프 기반)

메인 봇의 ClaudeAgentRunner와 동일한 패턴:
- 클래스 레벨 공유 이벤트 루프 (데몬 스레드)
- run_coroutine_threadsafe로 동기→비동기 브릿지
- _get_or_create_client / _remove_client로 클라이언트 생명주기 관리

#### 메서드

- `__init__(self)` (줄 73): 
- `_ensure_loop(cls)` (줄 78): 공유 이벤트 루프가 없거나 닫혀있으면 데몬 스레드에서 새로 생성
- `run_sync(self, coro)` (줄 96): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `run_claude_sync(self, prompt, session_id, thread_ts)` (줄 106): 동기 컨텍스트에서 Claude Code SDK를 호출합니다.
- `async _get_or_create_client(self, client_key, options)` (줄 118): 클라이언트를 가져오거나 새로 생성 (메인 봇 동일 패턴)
- `async _remove_client(self, client_key)` (줄 148): 클라이언트를 정리 (메인 봇 동일 패턴)
- `async _execute(self, prompt, session_id, thread_ts)` (줄 162): 실제 실행 로직 (메인 봇 _execute와 동일한 구조)

## 함수

### `run_claude_sync(prompt, session_id, thread_ts)`
- 위치: 줄 309
- 설명: 모듈 레벨 래퍼 — main.py 호환용

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
