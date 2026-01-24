# handlers/message.py

> 경로: `seosoyoung/handlers/message.py`

## 개요

스레드 메시지 핸들러

## 함수

### `_contains_bot_mention(text)`
- 위치: 줄 16
- 설명: 텍스트에 봇 멘션이 포함되어 있는지 확인

### `register_message_handlers(app, dependencies)`
- 위치: 줄 24
- 설명: 메시지 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.config.Config`
- `seosoyoung.handlers.translate.process_translate_message`
- `seosoyoung.slack.build_file_context`
- `seosoyoung.slack.download_files_sync`
