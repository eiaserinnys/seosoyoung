# slackbot/formatting.py

> 경로: `seosoyoung/slackbot/formatting.py`

## 개요

슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.

## 클래스

### `_CardLike` (Protocol)
- 위치: 줄 16
- 설명: 포맷팅에 필요한 최소 카드 속성

#### 메서드

- `card_name(self)` (줄 20): 
- `card_url(self)` (줄 23): 

## 함수

### `_emoji_thinking()`
- 위치: 줄 38
- 설명: thinking 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작

### `_emoji_tool()`
- 위치: 줄 43
- 설명: tool 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작

### `escape_backticks(text)`
- 위치: 줄 50
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

### `truncate_progress_text(text)`
- 위치: 줄 60
- 설명: 진행 상황 텍스트를 표시용으로 정리

### `format_as_blockquote(text)`
- 위치: 줄 70
- 설명: 텍스트를 슬랙 blockquote 형식으로 변환

### `build_trello_header(card, session_id)`
- 위치: 줄 77
- 설명: 트렐로 카드용 슬랙 메시지 헤더 생성

진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.
card가 None이면 카드 정보 없이 세션 ID만 표시합니다.

### `format_trello_progress(text, card, session_id)`
- 위치: 줄 89
- 설명: 트렐로 모드 채널 진행 상황 포맷

### `format_dm_progress(text, max_len)`
- 위치: 줄 96
- 설명: DM 스레드 진행 상황 포맷 (blockquote, 길이 제한)

### `format_thinking_initial()`
- 위치: 줄 106
- 설명: thinking 메시지 초기 포맷

### `format_thinking_text(text)`
- 위치: 줄 111
- 설명: thinking 메시지 텍스트 갱신 포맷

이모지 + bold 헤더 + code block으로 thinking 내용을 표시합니다.
슬랙에서 code block은 길어지면 자동 접힘(collapse)이 되어 스레드를 깔끔하게 유지합니다.

code block 내부에서 triple backtick(```)이 나타나면 외부 fence를 닫아 포맷이 깨지므로,
내부의 triple backtick은 유사 문자로 이스케이프합니다.

### `_summarize_tool_input(tool_input)`
- 위치: 줄 127
- 설명: tool_input을 간결한 한 줄 문자열로 요약

dict이면 주요 필드를 compact JSON으로,
그 외에는 str 변환 후 truncate합니다.

### `format_tool_initial(tool_name, tool_input)`
- 위치: 줄 147
- 설명: tool 메시지 초기 포맷

이모지 + bold tool_name 헤더를 표시하고,
tool_input이 있으면 blockquote로 요약을 덧붙입니다.

### `format_tool_complete(tool_name)`
- 위치: 줄 161
- 설명: tool 메시지 완료 포맷 (keep 모드)

### `format_tool_error(tool_name, error)`
- 위치: 줄 166
- 설명: tool 메시지 에러 포맷 (keep 모드)
