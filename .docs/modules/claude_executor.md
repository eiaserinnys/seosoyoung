# claude/executor.py

> 경로: `seosoyoung/claude/executor.py`

## 개요

Claude Code 실행 로직

_run_claude_in_session 함수를 캡슐화한 모듈입니다.

## 클래스

### `ClaudeExecutor`
- 위치: 줄 144
- 설명: Claude Code 실행기

세션 내에서 Claude Code를 실행하고 결과를 처리합니다.

#### 메서드

- `__init__(self, session_manager, get_session_lock, mark_session_running, mark_session_stopped, get_running_session_count, restart_manager, upload_file_to_slack, send_long_message, send_restart_confirmation)` (줄 150): 
- `run(self, session, prompt, msg_ts, channel, say, client, role, trello_card, is_existing_thread)` (줄 172): 세션 내에서 Claude Code 실행 (공통 로직)
- `_handle_success(self, result, session, effective_role, is_trello_mode, trello_card, channel, thread_ts, msg_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 360): 성공 결과 처리
- `_handle_trello_success(self, result, response, session, trello_card, channel, thread_ts, main_msg_ts, say, client)` (줄 386): 트렐로 모드 성공 처리
- `_handle_normal_success(self, result, response, channel, thread_ts, msg_ts, last_msg_ts, say, client, is_thread_reply)` (줄 434): 일반 모드(멘션) 성공 처리
- `_handle_restart_marker(self, result, session, thread_ts, say)` (줄 522): 재기동 마커 처리
- `_handle_error(self, error, is_trello_mode, trello_card, session, channel, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 545): 오류 결과 처리
- `_handle_exception(self, e, is_trello_mode, trello_card, session, channel, thread_ts, last_msg_ts, main_msg_ts, say, client, is_thread_reply)` (줄 588): 예외 처리

## 함수

### `get_runner_for_role(role)`
- 위치: 줄 20
- 설명: 역할에 맞는 ClaudeRunner/ClaudeAgentRunner 반환

### `_escape_backticks(text)`
- 위치: 줄 32
- 설명: 텍스트 내 모든 백틱을 이스케이프

슬랙에서 백틱은 인라인 코드(`)나 코드 블록(```)을 만드므로,
텍스트 내부에 백틱이 있으면 포맷팅이 깨집니다.
모든 백틱을 유사 문자(ˋ, modifier letter grave accent)로 대체합니다.

변환 규칙:
- ` (모든 백틱) → ˋ (U+02CB, modifier letter grave accent)

### `_parse_summary_details(response)`
- 위치: 줄 45
- 설명: 응답에서 요약과 상세 내용을 파싱

Args:
    response: Claude 응답 텍스트

Returns:
    (summary, details, remainder): 요약, 상세, 나머지 텍스트
    - 마커가 없으면 (None, None, response) 반환

### `_add_reaction(client, channel, ts, emoji)`
- 위치: 줄 88
- 설명: 슬랙 메시지에 이모지 리액션 추가

Args:
    client: Slack client
    channel: 채널 ID
    ts: 메시지 타임스탬프
    emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

Returns:
    성공 여부

### `_remove_reaction(client, channel, ts, emoji)`
- 위치: 줄 108
- 설명: 슬랙 메시지에서 이모지 리액션 제거

Args:
    client: Slack client
    channel: 채널 ID
    ts: 메시지 타임스탬프
    emoji: 이모지 이름 (콜론 없이, 예: "thought_balloon")

Returns:
    성공 여부

### `_build_trello_header(card, session_id)`
- 위치: 줄 128
- 설명: 트렐로 카드용 슬랙 메시지 헤더 생성

진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

Args:
    card: TrackedCard 정보
    session_id: 세션 ID (표시용)

Returns:
    헤더 문자열

## 내부 의존성

- `seosoyoung.claude.get_claude_runner`
- `seosoyoung.claude.session.Session`
- `seosoyoung.claude.session.SessionManager`
- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.trello.watcher.TrackedCard`
