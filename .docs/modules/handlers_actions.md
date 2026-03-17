# handlers/actions.py

> 경로: `seosoyoung/slackbot/handlers/actions.py`

## 개요

재시작 버튼, AskUserQuestion 응답, 크레덴셜 프로필 관리 액션 핸들러

## 함수

### `send_restart_confirmation(client, channel, restart_type, running_count, user_id, original_thread_ts)`
- 위치: 줄 15
- 설명: 재시작 확인 메시지를 인터랙티브 버튼과 함께 전송

Args:
    client: Slack client
    channel: 알림 채널 ID
    restart_type: 재시작 유형
    running_count: 실행 중인 대화 수
    user_id: 요청한 사용자 ID
    original_thread_ts: 원래 요청 메시지의 스레드 ts (있으면)

### `send_deploy_shutdown_popup(client, channel, running_count, restart_type)`
- 위치: 줄 83
- 설명: 배포/재시작 시 활성 세션이 있을 때 사용자 확인 팝업을 전송

supervisor에서 graceful shutdown 요청이 왔을 때 활성 세션이 있으면
사용자에게 즉시 종료 또는 세션 완료 후 종료를 선택하도록 한다.

Args:
    client: Slack client
    channel: 알림 채널 ID
    running_count: 실행 중인 세션 수
    restart_type: 재시작 유형

### `register_action_handlers(app, dependencies)`
- 위치: 줄 146
- 설명: 액션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

### `_deliver_input_response_to_soul(agent_session_id, request_id, question_text, selected_label)`
- 위치: 줄 387
- 설명: soul-server에 AskUserQuestion 응답을 HTTP로 전달

POST /sessions/{agent_session_id}/respond
Body: {"request_id": "...", "answers": {"question_text": "selected_label"}}

### `activate_credential_profile(profile_name, channel, message_ts, client)`
- 위치: 줄 429
- 설명: 크레덴셜 프로필 전환 처리

Soul API를 호출하여 프로필을 활성화하고 슬랙 메시지를 업데이트합니다.

Args:
    profile_name: 활성화할 프로필 이름
    channel: 슬랙 채널 ID
    message_ts: 원본 메시지 타임스탬프
    client: Slack client

### `save_credential_profile(profile_name, channel, message_ts, client)`
- 위치: 줄 481
- 설명: 크레덴셜 프로필 저장 처리

Soul API를 호출하여 현재 크레덴셜을 프로필로 저장하고
슬랙 메시지를 업데이트합니다.

Args:
    profile_name: 저장할 프로필 이름
    channel: 슬랙 채널 ID
    message_ts: 원본 메시지 타임스탬프
    client: Slack client

### `delete_credential_profile(profile_name, channel, message_ts, client)`
- 위치: 줄 536
- 설명: 크레덴셜 프로필 삭제 처리

Soul API를 호출하여 프로필을 삭제하고 슬랙 메시지를 업데이트합니다.

Args:
    profile_name: 삭제할 프로필 이름
    channel: 슬랙 채널 ID
    message_ts: 원본 메시지 타임스탬프
    client: Slack client

### `list_credential_profiles(channel, message_ts, client)`
- 위치: 줄 590
- 설명: 크레덴셜 프로필 목록 조회 및 관리 UI 표시

Soul API에서 프로필 목록과 rate limit 정보를 조회하여
프로필 관리 블록을 슬랙 메시지로 업데이트합니다.

Args:
    channel: 슬랙 채널 ID
    message_ts: 원본 메시지 타임스탬프
    client: Slack client

### `register_credential_action_handlers(app, dependencies)`
- 위치: 줄 676
- 설명: 크레덴셜 프로필 관리 액션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리 (현재 미사용, 확장성을 위해 유지)

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.restart.RestartRequest`
- `seosoyoung.slackbot.restart.RestartType`
