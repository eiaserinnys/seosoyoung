# rescue/engine_adapter.py

> 경로: `seosoyoung/rescue/engine_adapter.py`

## 개요

rescue-bot 엔진 어댑터

rescue.claude.agent_runner의 ClaudeRunner를 rescue-bot용으로 래핑합니다.
rescue-bot 전용 설정(working_dir, 도구 제한)을 적용하여
ClaudeRunner 인스턴스를 생성하고, interrupt/compact 등의 제어를 위임합니다.

채널/스레드 정보는 메인 봇과 동일하게 프롬프트 내 <slack-context> 블록을 통해
Claude에 전달되며, env 주입은 사용하지 않습니다.

## 함수

### `create_runner(thread_ts)`
- 위치: 줄 28
- 설명: rescue-bot용 ClaudeRunner를 생성합니다.

Args:
    thread_ts: 스레드 타임스탬프 (세션 키)

### `interrupt(thread_ts)`
- 위치: 줄 42
- 설명: 실행 중인 스레드에 인터럽트 전송

### `compact_session_sync(session_id)`
- 위치: 줄 50
- 설명: 세션 컴팩트 (동기)

## 내부 의존성

- `seosoyoung.rescue.claude.agent_runner.ClaudeRunner`
- `seosoyoung.rescue.claude.agent_runner.get_runner`
- `seosoyoung.rescue.claude.engine_types.EngineResult`
- `seosoyoung.rescue.config.RescueConfig`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
