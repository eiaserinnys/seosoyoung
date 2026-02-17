# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (세션 재개 지원)

메인 봇의 agent_runner.py에서 OM, 인터벤션, 스트리밍 콜백 등을
제거한 최소 구현입니다. ClaudeSDKClient 기반으로 세션 재개를 지원합니다.

## 클래스

### `RescueResult`
- 위치: 줄 44
- 설명: 실행 결과

## 함수

### `run_claude_sync(prompt, session_id)`
- 위치: 줄 53
- 설명: 동기 컨텍스트에서 Claude Code SDK를 호출합니다.

Slack 이벤트 핸들러(동기)에서 직접 호출할 수 있습니다.
내부적으로 asyncio.run()을 사용하여 매 호출마다 새 이벤트 루프를 생성합니다.

resume 실패 시 새 세션으로 자동 폴백합니다.

### `async _run_claude(prompt, session_id)`
- 위치: 줄 74
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
