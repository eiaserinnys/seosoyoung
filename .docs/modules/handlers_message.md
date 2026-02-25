# handlers/message.py

> 경로: `seosoyoung/slackbot/handlers/message.py`

## 개요

스레드 메시지 핸들러 + DM 채널 핸들러

## 함수

### `build_slack_context(channel, user_id, thread_ts, parent_thread_ts)`
- 위치: 줄 21
- 설명: 슬랙 컨텍스트 블록 문자열을 생성합니다.

Args:
    channel: 채널 ID
    user_id: 사용자 ID
    thread_ts: 현재 메시지의 스레드 타임스탬프
    parent_thread_ts: 상위 스레드 타임스탬프 (스레드 내 메시지인 경우)

### `process_thread_message(event, text, thread_ts, ts, channel, session, say, client, get_user_role, run_claude_in_session, log_prefix, channel_store, session_manager)`
- 위치: 줄 47
- 설명: 세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

mention.py와 message.py에서 공유합니다.

Returns:
    True if processed, False if skipped (empty message)

### `_contains_bot_mention(text)`
- 위치: 줄 130
- 설명: 텍스트에 봇 멘션이 포함되어 있는지 확인

### `_handle_dm_message(event, say, client, dependencies)`
- 위치: 줄 138
- 설명: DM 채널 메시지 처리

앱 DM에서 보낸 메시지를 일반 채널 멘션과 동일하게 처리합니다.
- 첫 메시지 (thread_ts 없음): 명령어 처리 또는 세션 생성 + Claude 실행
- 스레드 메시지 (thread_ts 있음): 기존 세션에서 후속 처리

### `register_message_handlers(app, dependencies)`
- 위치: 줄 212
- 설명: 메시지 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

### `_contains_trigger_word(text)`
- 위치: 줄 497
- 설명: 텍스트에 트리거 워드가 포함되어 있는지 확인합니다.

### `_maybe_trigger_digest(channel_id, client, store, observer, compressor, cooldown)`
- 위치: 줄 505
- 설명: pending 토큰이 threshold_A 이상이면 별도 스레드에서 파이프라인을 실행합니다.

force=True이면 임계치와 무관하게 즉시 트리거합니다.

### `_send_collect_log(client, channel_id, store, event)`
- 위치: 줄 562
- 설명: 수집 디버그 로그를 전송합니다.

## 내부 의존성

- `seosoyoung.slackbot.claude.get_claude_runner`
- `seosoyoung.slackbot.claude.session_context.build_followup_context`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.handlers.translate.process_translate_message`
- `seosoyoung.slackbot.slack.build_file_context`
- `seosoyoung.slackbot.slack.download_files_sync`
- `seosoyoung.slackbot.slack.message_formatter.format_slack_message`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
