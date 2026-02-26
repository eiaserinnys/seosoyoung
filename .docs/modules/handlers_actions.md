# handlers/actions.py

> 경로: `seosoyoung/slackbot/handlers/actions.py`

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

### `send_deploy_shutdown_popup(client, channel, running_count, restart_type)`
- 위치: 줄 79
- 설명: 배포/재시작 시 활성 세션이 있을 때 사용자 확인 팝업을 전송

supervisor에서 graceful shutdown 요청이 왔을 때 활성 세션이 있으면
사용자에게 즉시 종료 또는 세션 완료 후 종료를 선택하도록 한다.

Args:
    client: Slack client
    channel: 알림 채널 ID
    running_count: 실행 중인 세션 수
    restart_type: 재시작 유형

### `register_action_handlers(app, dependencies)`
- 위치: 줄 142
- 설명: 액션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.restart.RestartRequest`
- `seosoyoung.slackbot.restart.RestartType`
