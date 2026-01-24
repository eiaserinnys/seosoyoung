# handlers/actions.py

> 경로: `seosoyoung/handlers/actions.py`

## 개요

재시작 버튼 액션 핸들러

## 함수

### `send_restart_confirmation(client, channel, restart_type, running_count, user_id, original_thread_ts)`
- 위치: 줄 11
- 설명: 재시작 확인 메시지를 인터랙티브 버튼과 함께 전송

Args:
    client: Slack client
    channel: 알림 채널 ID
    restart_type: 재시작 유형
    running_count: 실행 중인 대화 수
    user_id: 요청한 사용자 ID
    original_thread_ts: 원래 요청 메시지의 스레드 ts (있으면)

### `register_action_handlers(app, dependencies)`
- 위치: 줄 79
- 설명: 액션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartRequest`
- `seosoyoung.restart.RestartType`
