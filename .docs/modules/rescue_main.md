# rescue/main.py

> 경로: `seosoyoung/rescue/main.py`

## 개요

rescue-bot 메인 모듈

슬랙 멘션 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.

## 함수

### `_get_thread_lock(thread_ts)`
- 위치: 줄 35
- 설명: 스레드별 락을 가져오거나 생성

### `_strip_mention(text, bot_user_id)`
- 위치: 줄 43
- 설명: 멘션 태그를 제거하고 순수 텍스트만 반환

### `handle_mention(event, say, client)`
- 위치: 줄 53
- 데코레이터: app.event
- 설명: 멘션 이벤트 핸들러

멘션을 받으면 Claude Code SDK를 호출하고 결과를 스레드에 응답합니다.

### `main()`
- 위치: 줄 130
- 설명: rescue-bot 진입점

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
- `seosoyoung.rescue.runner.run_claude`
