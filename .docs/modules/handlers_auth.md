# handlers/auth.py

> 경로: `seosoyoung/slackbot/handlers/auth.py`

## 개요

Claude 인증 명령어 핸들러

setup-token, clear-token 명령어와 스레드 내 인증 코드 감지를 처리합니다.

## 함수

### `_run_soul_api(async_fn)`
- 위치: 줄 21
- 설명: SoulServiceClient API를 동기적으로 호출

Args:
    async_fn: SoulServiceClient 인스턴스를 받아 코루틴을 반환하는 함수

Returns:
    API 응답

### `handle_setup_token()`
- 위치: 줄 43
- 설명: setup-token 명령어 핸들러

1. 스레드 생성 + soulstream POST /auth/claude/start 호출
2. 스레드에 URL + 안내 메시지 전송

### `handle_clear_token()`
- 위치: 줄 98
- 설명: clear-token 명령어 핸들러

soulstream DELETE /auth/claude/token 호출

### `check_auth_session(thread_ts, text, say, client, dependencies)`
- 위치: 줄 129
- 설명: 인증 세션에서 코드 입력 감지. 처리했으면 True 반환.

Args:
    thread_ts: 스레드 타임스탬프
    text: 메시지 텍스트
    say: 응답 함수
    client: Slack 클라이언트
    dependencies: 의존성 딕셔너리

Returns:
    True if handled, False otherwise

### `get_active_auth_sessions()`
- 위치: 줄 192
- 설명: 활성 인증 세션 조회 (테스트용)

### `clear_auth_sessions()`
- 위치: 줄 197
- 설명: 모든 인증 세션 초기화 (테스트용)

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.soulstream.service_client.SoulServiceClient`
- `seosoyoung.slackbot.soulstream.service_client.SoulServiceError`
