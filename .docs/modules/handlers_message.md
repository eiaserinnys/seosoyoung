# handlers/message.py

> 경로: `seosoyoung/handlers/message.py`

## 개요

스레드 메시지 핸들러

## 함수

### `process_thread_message(event, text, thread_ts, ts, channel, session, say, client, get_user_role, run_claude_in_session, log_prefix)`
- 위치: 줄 19
- 설명: 세션이 있는 스레드에서 메시지를 처리하는 공통 로직.

mention.py와 message.py에서 공유합니다.

Returns:
    True if processed, False if skipped (empty message)

### `_contains_bot_mention(text)`
- 위치: 줄 69
- 설명: 텍스트에 봇 멘션이 포함되어 있는지 확인

### `register_message_handlers(app, dependencies)`
- 위치: 줄 77
- 설명: 메시지 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

### `_maybe_trigger_digest(channel_id, client, store, observer, compressor, cooldown)`
- 위치: 줄 325
- 설명: 버퍼 토큰 임계치를 초과하면 별도 스레드에서 소화 파이프라인을 실행합니다.

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.config.Config`
- `seosoyoung.handlers.translate.process_translate_message`
- `seosoyoung.slack.build_file_context`
- `seosoyoung.slack.download_files_sync`
