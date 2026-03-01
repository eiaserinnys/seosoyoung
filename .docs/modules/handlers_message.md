# handlers/message.py

> 경로: `seosoyoung/slackbot/handlers/message.py`

## 개요

스레드 메시지 핸들러 + DM 채널 핸들러

## 함수

### `build_slack_context(channel, user_id, thread_ts, parent_thread_ts)`
- 위치: 줄 16
- 설명: 슬랙 컨텍스트 블록 문자열을 생성합니다.

Args:
    channel: 채널 ID
    user_id: 사용자 ID
    thread_ts: 현재 메시지의 스레드 타임스탬프
    parent_thread_ts: 상위 스레드 타임스탬프 (스레드 내 메시지인 경우)

### `_get_plugin_instance(pm, name)`
- 위치: 줄 42
- 설명: PluginManager에서 플러그인 인스턴스를 가져옵니다.

### `process_thread_message(event, text, thread_ts, ts, channel, session, say, client, get_user_role, run_claude_in_session, log_prefix, session_manager, update_message_fn, plugin_manager)`
- 위치: 줄 49
- 설명: 세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

mention.py와 message.py에서 공유합니다.
Memory injection과 observation은 plugin hooks로 처리합니다.

Returns:
    True if processed, False if skipped (empty message)

### `_contains_bot_mention(text)`
- 위치: 줄 256
- 설명: 텍스트에 봇 멘션이 포함되어 있는지 확인

### `_handle_dm_message(event, say, client, dependencies)`
- 위치: 줄 264
- 설명: DM 채널 메시지 처리

앱 DM에서 보낸 메시지를 일반 채널 멘션과 동일하게 처리합니다.
- 첫 메시지 (thread_ts 없음): 명령어 처리 또는 세션 생성 + Claude 실행
- 스레드 메시지 (thread_ts 있음): 기존 세션에서 후속 처리

### `register_message_handlers(app, dependencies)`
- 위치: 줄 340
- 설명: 메시지 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.core.context.create_hook_context`
- `seosoyoung.slackbot.claude.session_context.build_followup_context`
- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.slack.build_file_context`
- `seosoyoung.slackbot.slack.download_files_sync`
- `seosoyoung.slackbot.slack.message_formatter.format_slack_message`
- `seosoyoung.utils.async_bridge.run_in_new_loop`
