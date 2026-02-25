# claude/message_formatter.py

> 경로: `seosoyoung/slackbot/claude/message_formatter.py`

## 개요

슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
- 백틱 이스케이프
- 트렐로 헤더
- 진행 상황(on_progress) 포맷팅

순수 텍스트 변환 함수들은 slackbot.formatting으로 추출되었습니다.
이 모듈은 하위호환을 위해 re-export합니다.

## 내부 의존성

- `seosoyoung.slackbot.formatting.DM_MSG_MAX_LEN`
- `seosoyoung.slackbot.formatting.PROGRESS_MAX_LEN`
- `seosoyoung.slackbot.formatting.SLACK_MSG_MAX_LEN`
- `seosoyoung.slackbot.formatting.build_trello_header`
- `seosoyoung.slackbot.formatting.escape_backticks`
- `seosoyoung.slackbot.formatting.format_as_blockquote`
- `seosoyoung.slackbot.formatting.format_dm_progress`
- `seosoyoung.slackbot.formatting.format_trello_progress`
- `seosoyoung.slackbot.formatting.truncate_progress_text`
