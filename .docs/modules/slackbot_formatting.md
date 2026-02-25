# slackbot/formatting.py

> 경로: `seosoyoung/slackbot/formatting.py`

## 개요

슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.

## 클래스

### `_CardLike` (Protocol)
- 위치: 줄 14
- 설명: 포맷팅에 필요한 최소 카드 속성

#### 메서드

- `card_name(self)` (줄 18): 
- `card_url(self)` (줄 21): 

## 함수

### `escape_backticks(text)`
- 위치: 줄 33
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

### `truncate_progress_text(text)`
- 위치: 줄 43
- 설명: 진행 상황 텍스트를 표시용으로 정리

### `format_as_blockquote(text)`
- 위치: 줄 53
- 설명: 텍스트를 슬랙 blockquote 형식으로 변환

### `build_trello_header(card, session_id)`
- 위치: 줄 60
- 설명: 트렐로 카드용 슬랙 메시지 헤더 생성

진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

### `format_trello_progress(text, card, session_id)`
- 위치: 줄 69
- 설명: 트렐로 모드 채널 진행 상황 포맷

### `format_dm_progress(text, max_len)`
- 위치: 줄 76
- 설명: DM 스레드 진행 상황 포맷 (blockquote, 길이 제한)
