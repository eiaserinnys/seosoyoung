# slackbot/formatting.py

> 경로: `seosoyoung/slackbot/formatting.py`

## 개요

슬랙 메시지 포맷팅 — 공유 리프 모듈

순수 텍스트 변환 함수를 모아둔 모듈입니다.
claude/, presentation/ 등 여러 패키지에서 공통으로 사용합니다.

이 모듈은 seosoyoung 내부 의존성이 없는 리프(leaf) 모듈이어야 합니다.

## 클래스

### `_CardLike` (Protocol)
- 위치: 줄 17
- 설명: 포맷팅에 필요한 최소 카드 속성

#### 메서드

- `card_name(self)` (줄 21): 
- `card_url(self)` (줄 24): 

## 함수

### `_emoji_thinking()`
- 위치: 줄 43
- 설명: thinking 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작

### `_emoji_tool()`
- 위치: 줄 48
- 설명: tool 이모지 — 호출 시점에 환경변수를 읽어 dotenv 로딩 순서에 무관하게 동작

### `_emoji_thinking_done()`
- 위치: 줄 53
- 설명: thinking 완료 이모지

### `_emoji_tool_done()`
- 위치: 줄 58
- 설명: tool 완료 이모지

### `escape_backticks(text)`
- 위치: 줄 65
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

### `truncate_progress_text(text)`
- 위치: 줄 75
- 설명: 진행 상황 텍스트를 표시용으로 정리

### `_normalize_newlines(text)`
- 위치: 줄 85
- 설명: 연속 빈 줄을 단일 빈 줄로 정규화

3줄 이상의 연속 줄바꿈을 2줄(= 빈 줄 하나)로 줄입니다.
슬랙 mrkdwn에서 연속 빈 줄이 blockquote 구조를 깨뜨리는 것을 방지합니다.

### `_quote_lines(text)`
- 위치: 줄 94
- 설명: 이미 escape된 텍스트를 슬랙 blockquote로 변환 (> prefix per line)

연속 빈 줄을 정규화한 후, 모든 줄에 ``> `` prefix를 붙입니다.

### `format_as_blockquote(text)`
- 위치: 줄 103
- 설명: 텍스트를 슬랙 blockquote 형식으로 변환

### `build_trello_header(card, session_id)`
- 위치: 줄 108
- 설명: 트렐로 카드용 슬랙 메시지 헤더 생성

진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.
card가 None이면 카드 정보 없이 세션 ID만 표시합니다.

### `format_trello_progress(text, card, session_id)`
- 위치: 줄 120
- 설명: 트렐로 모드 채널 진행 상황 포맷

### `format_dm_progress(text, max_len)`
- 위치: 줄 127
- 설명: DM 스레드 진행 상황 포맷 (blockquote, 길이 제한)

### `format_initial_placeholder()`
- 위치: 줄 137
- 설명: 소울스트림 요청 전송 직후 표시할 대기 메시지

### `format_thinking_initial()`
- 위치: 줄 142
- 설명: thinking 메시지 초기 포맷

### `_format_thinking_body(text, emoji_fn)`
- 위치: 줄 147
- 설명: thinking 포맷 공통 로직 — 이모지 함수만 다름

### `format_thinking_text(text)`
- 위치: 줄 159
- 설명: thinking 메시지 텍스트 갱신 포맷

이모지 + bold 헤더 + blockquote로 thinking 내용을 표시합니다.
길이 초과 시 뒤에서 잘라서 최신 내용을 표시합니다.

### `format_thinking_complete(text)`
- 위치: 줄 168
- 설명: thinking 완료 포맷 — done 이모지로 교체한 최종 상태

빈 텍스트도 처리하므로 호출자는 text_buffer 유무를 검사하지 않고
항상 format_thinking_complete(text) 호출 가능.

### `_format_tool_input_readable(tool_input)`
- 위치: 줄 177
- 설명: tool_input을 human-readable blockquote로 변환

dict이면 key/value 쌍을 개별 줄로 나열하고,
그 외에는 str 변환 후 단일 blockquote로 표시합니다.

value에 줄바꿈이 포함되어 있으면 모든 줄에 ``> `` prefix를 붙여서
슬랙 blockquote가 중간에 끊기지 않도록 합니다.

### `format_tool_initial(tool_name, tool_input)`
- 위치: 줄 210
- 설명: tool 메시지 초기 포맷

이모지 + bold tool_name 헤더를 표시하고,
tool_input이 있으면 human-readable blockquote로 key/value를 나열합니다.

### `_stringify_result(result)`
- 위치: 줄 224
- 설명: result를 읽기 쉬운 문자열로 변환

### `format_tool_result(tool_name, result, is_error)`
- 위치: 줄 238
- 설명: tool result 도착 시 표시 포맷

성공 시 done 이모지 + 결과 blockquote,
에러 시 :x: + 에러 메시지 blockquote.

### `format_tool_complete(tool_name)`
- 위치: 줄 261
- 설명: tool 메시지 완료 포맷 (결과 없이 이름만)
