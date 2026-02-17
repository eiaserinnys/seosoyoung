# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 ClaudeAgentRunner와 동일한 공유 이벤트 루프 패턴을 사용합니다.
ClaudeSDKClient 기반으로 세션 재개를 지원합니다.

## 클래스

### `RescueResult`
- 위치: 줄 48
- 설명: 실행 결과

### `RescueRunner`
- 위치: 줄 57
- 설명: Claude Code SDK 실행기 (공유 이벤트 루프 기반)

메인 봇의 ClaudeAgentRunner와 동일한 패턴:
- 클래스 레벨 공유 이벤트 루프 (데몬 스레드)
- run_coroutine_threadsafe로 동기→비동기 브릿지
- 매 실행마다 ClaudeSDKClient connect → query → receive → disconnect

#### 메서드

- `_ensure_loop(cls)` (줄 72): 공유 이벤트 루프가 없거나 닫혀있으면 데몬 스레드에서 새로 생성
- `run_sync(self, coro)` (줄 90): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `run_claude_sync(self, prompt, session_id)` (줄 100): 동기 컨텍스트에서 Claude Code SDK를 호출합니다.
- `async _run_claude(self, prompt, session_id)` (줄 111): Claude Code SDK를 호출하고 결과를 반환합니다.

## 함수

### `run_claude_sync(prompt, session_id)`
- 위치: 줄 234
- 설명: 모듈 레벨 래퍼 — main.py 호환용

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
