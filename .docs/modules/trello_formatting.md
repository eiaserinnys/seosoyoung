# trello/formatting.py

> 경로: `seosoyoung/slackbot/trello/formatting.py`

## 개요

트렐로 카드 포맷팅 유틸리티

체크리스트, 코멘트를 프롬프트용 문자열로 변환하는 순수 함수들을 제공합니다.

## 함수

### `format_checklists(checklists)`
- 위치: 줄 7
- 설명: 체크리스트를 프롬프트용 문자열로 포맷

Args:
    checklists: Trello API에서 반환된 체크리스트 목록

Returns:
    마크다운 형식의 체크리스트 문자열

### `format_comments(comments)`
- 위치: 줄 28
- 설명: 코멘트를 프롬프트용 문자열로 포맷

Args:
    comments: Trello API에서 반환된 코멘트 목록

Returns:
    마크다운 형식의 코멘트 문자열
