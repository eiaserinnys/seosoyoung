# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 agent_runner.py에서 OM, 인터벤션, 스트리밍 콜백 등을
제거한 최소 구현입니다. ClaudeSDKClient 기반으로 세션 재개를 지원합니다.

## 클래스

### `RescueResult`
- 위치: 줄 45
- 설명: 실행 결과

## 함수

### `_ensure_loop()`
- 위치: 줄 60
- 설명: 공유 이벤트 루프가 없으면 데몬 스레드에서 생성

### `run_sync(coro)`
- 위치: 줄 81
- 설명: 동기 컨텍스트에서 코루틴을 실행하는 브릿지

Slack 이벤트 핸들러(동기)에서 async 함수를 호출할 때 사용합니다.

### `async run_claude(prompt, session_id)`
- 위치: 줄 91
- 설명: Claude Code SDK를 호출하고 결과를 반환합니다.

ClaudeSDKClient 기반으로 세션 재개를 지원합니다:
- session_id가 None이면 새 세션을 시작합니다.
- session_id가 있으면 해당 세션을 이어서 실행합니다.

Args:
    prompt: 실행할 프롬프트
    session_id: 이어갈 세션 ID (선택)

Returns:
    RescueResult (session_id 포함)

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
