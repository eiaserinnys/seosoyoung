# claude/message_formatter.py

> 경로: `seosoyoung/claude/message_formatter.py`

## 개요

슬랙 메시지 포맷팅 유틸리티

Claude 응답을 슬랙 메시지 형식으로 변환하는 함수들을 제공합니다.

## 함수

### `escape_backticks(text)`
- 위치: 줄 10
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

변환 규칙:
- ` (모든 백틱) → ˋ (U+02CB, modifier letter grave accent)

Args:
    text: 변환할 텍스트

Returns:
    백틱이 이스케이프된 텍스트

### `parse_summary_details(response)`
- 위치: 줄 29
- 설명: 응답에서 요약과 상세 내용을 파싱

Args:
    response: Claude 응답 텍스트

Returns:
    (summary, details, remainder): 요약, 상세, 나머지 텍스트
    - 마커가 없으면 (None, None, response) 반환

### `strip_summary_details_markers(response)`
- 위치: 줄 63
- 설명: 응답에서 SUMMARY/DETAILS 마커만 제거하고 내용은 유지

스레드 내 후속 대화에서 마커 태그를 제거할 때 사용.
마커 제거 후 빈 줄만 남으면 해당 줄도 삭제.

Args:
    response: Claude 응답 텍스트

Returns:
    마커가 제거된 텍스트

### `build_trello_header(card, session_id)`
- 위치: 줄 87
- 설명: 트렐로 카드용 슬랙 메시지 헤더 생성

진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

Args:
    card: TrackedCard 정보
    session_id: 세션 ID (표시용)

Returns:
    헤더 문자열

## 내부 의존성

- `seosoyoung.trello.watcher.TrackedCard`
