# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 경량 실행기

메인 봇의 agent_runner.py에서 OM, 인터벤션, 스트리밍 콜백 등을
제거한 최소 구현입니다.

## 클래스

### `RescueResult`
- 위치: 줄 43
- 설명: 실행 결과

## 함수

### `async run_claude(prompt)`
- 위치: 줄 51
- 설명: Claude Code SDK를 호출하고 결과를 반환합니다.

Stateless: 세션 재개, OM, 인터벤션 등 없이 단발 호출만 수행합니다.

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
