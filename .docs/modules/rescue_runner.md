# rescue/runner.py

> 경로: `seosoyoung/rescue/runner.py`

## 개요

Claude Code SDK 실행기 (메인 봇 기본 대화 기능 완전 복제)

메인 봇의 ClaudeAgentRunner에서 핵심 로직을 복제한 버전:
- _classify_process_error: ProcessError를 사용자 친화적 메시지로 변환
- _build_options: ClaudeCodeOptions 생성 (env 주입, PreCompact 훅, stderr 캡처)
- _get_or_create_client / _remove_client: 클라이언트 생명주기 관리
- _execute: on_progress 콜백, on_compact, rate_limit 처리
- interrupt / compact_session: 세션 제어
- run / run_sync: async/sync 인터페이스

제외: OM, Recall, 트렐로 연동, 번역, 채널 관찰, 프로필, 정주행, NPC, Remote 모드

## 클래스

### `RescueResult`
- 위치: 줄 81
- 설명: 실행 결과

### `RescueRunner`
- 위치: 줄 92
- 설명: Claude Code SDK 실행기 (메인 봇 기본 대화 기능 복제)

메인 봇의 ClaudeAgentRunner와 동일한 패턴:
- run_in_new_loop로 각 실행마다 격리된 이벤트 루프 사용
- _get_or_create_client / _remove_client로 클라이언트 생명주기 관리
- on_progress / on_compact 콜백
- interrupt / compact_session

#### 메서드

- `__init__(self)` (줄 102): 
- `run_sync(self, coro)` (줄 108): 동기 컨텍스트에서 코루틴을 실행하는 브릿지
- `_build_options(self, session_id, channel, thread_ts, compact_events)` (줄 115): ClaudeCodeOptions를 생성합니다.
- `async _get_or_create_client(self, client_key, options)` (줄 195): 클라이언트를 가져오거나 새로 생성
- `async _remove_client(self, client_key)` (줄 222): 클라이언트를 정리 (disconnect 후 딕셔너리에서 제거)
- `interrupt(self, thread_ts)` (줄 234): 실행 중인 스레드에 인터럽트 전송 (동기)
- `async compact_session(self, session_id)` (줄 257): 세션 컴팩트 처리
- `async run(self, prompt, session_id, thread_ts, channel, on_progress, on_compact)` (줄 283): Claude Code 실행 (async, lock 포함)
- `async _execute(self, prompt, session_id, thread_ts, channel, on_progress, on_compact)` (줄 303): 실제 실행 로직 (메인 봇 _execute와 동일한 구조)

## 함수

### `_classify_process_error(e)`
- 위치: 줄 53
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

### `get_runner()`
- 위치: 줄 462
- 설명: 모듈 레벨 RescueRunner 인스턴스를 반환

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
