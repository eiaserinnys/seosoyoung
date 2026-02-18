# rescue/message_formatter.py

> 경로: `seosoyoung/rescue/message_formatter.py`

## 개요

슬랙 메시지 포맷팅 유틸리티 (rescue-bot 경량 버전)

메인 봇의 message_formatter.py에서 Trello 관련 기능을 제외한 버전입니다.

## 함수

### `build_context_usage_bar(usage, bar_length)`
- 위치: 줄 13
- 설명: usage dict에서 컨텍스트 사용량 바를 생성

Args:
    usage: ResultMessage.usage dict
    bar_length: 바의 전체 칸 수

Returns:
    "Context | ■■■■■■□□□□□□□□□□□□□□ | 30%" 형태 문자열, 또는 None

### `escape_backticks(text)`
- 위치: 줄 42
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

### `parse_summary_details(response)`
- 위치: 줄 52
- 설명: 응답에서 요약과 상세 내용을 파싱

Args:
    response: Claude 응답 텍스트

Returns:
    (summary, details, remainder): 요약, 상세, 나머지 텍스트
    - 마커가 없으면 (None, None, response) 반환

### `strip_summary_details_markers(response)`
- 위치: 줄 86
- 설명: 응답에서 SUMMARY/DETAILS 마커만 제거하고 내용은 유지

스레드 내 후속 대화에서 마커 태그를 제거할 때 사용.
