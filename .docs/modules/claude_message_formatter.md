# claude/message_formatter.py

> 경로: `seosoyoung/slackbot/claude/message_formatter.py`

## 개요

슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.
- 컨텍스트 사용량 바
- 백틱 이스케이프
- 트렐로 헤더
- 진행 상황(on_progress) 포맷팅

순수 텍스트 변환 함수들은 slackbot.formatting으로 추출되었습니다.
이 모듈은 하위호환을 위해 re-export합니다.

## 함수

### `build_context_usage_bar(usage, bar_length)`
- 위치: 줄 34
- 설명: usage dict에서 컨텍스트 사용량 바를 생성

SDK의 ResultMessage.usage 구조:
- input_tokens: 캐시 미스분 (새로 보낸 토큰)
- cache_creation_input_tokens: 이번 턴에 새로 캐시에 쓴 토큰
- cache_read_input_tokens: 캐시에서 읽은 토큰
→ 실제 컨텍스트 크기 = 세 값의 합

Args:
    usage: ResultMessage.usage dict
    bar_length: 바의 전체 칸 수

Returns:
    "Context | ■■■■■■□□□□□□□□□□□□□□ | 30%" 형태 문자열, 또는 None

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
