# rescue/main.py

> 경로: `seosoyoung/rescue/main.py`

## 개요

rescue-bot 메인 모듈

슬랙 멘션/스레드 메시지 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.

세션 관리:
- 스레드 ts를 키로 session_id를 in-memory dict에 저장
- 스레드 내 후속 대화(멘션 또는 일반 메시지)에서 세션을 이어감

## 함수

### `_get_thread_lock(thread_ts)`
- 위치: 줄 42
- 설명: 스레드별 락을 가져오거나 생성

### `_get_session_id(thread_ts)`
- 위치: 줄 50
- 설명: 스레드의 세션 ID를 조회

### `_set_session_id(thread_ts, session_id)`
- 위치: 줄 56
- 설명: 스레드의 세션 ID를 저장

### `_strip_mention(text, bot_user_id)`
- 위치: 줄 62
- 설명: 멘션 태그를 제거하고 순수 텍스트만 반환

### `_contains_bot_mention(text)`
- 위치: 줄 71
- 설명: 텍스트에 봇 멘션이 포함되어 있는지 확인

### `_process_message(prompt, thread_ts, channel, say, client)`
- 위치: 줄 78
- 설명: 공통 메시지 처리 로직

멘션/메시지 핸들러에서 공유합니다.
세션이 있으면 이어서 실행하고, 결과의 session_id를 저장합니다.

### `handle_mention(event, say, client)`
- 위치: 줄 151
- 데코레이터: app.event
- 설명: 멘션 이벤트 핸들러

멘션을 받으면 Claude Code SDK를 호출하고 결과를 스레드에 응답합니다.
기존 세션이 있으면 이어서 실행합니다.

### `handle_message(event, say, client)`
- 위치: 줄 178
- 데코레이터: app.event
- 설명: 스레드 메시지 핸들러

세션이 있는 스레드 내 일반 메시지(멘션 없이)를 처리합니다.

### `main()`
- 위치: 줄 220
- 설명: rescue-bot 진입점

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
- `seosoyoung.rescue.runner.run_claude_sync`
