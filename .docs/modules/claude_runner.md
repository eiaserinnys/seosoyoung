# claude/runner.py

> 경로: `seosoyoung/claude/runner.py`

## 개요

Claude Code CLI 래퍼

## 클래스

### `ClaudeResult`
- 위치: 줄 43
- 설명: Claude Code 실행 결과

### `ClaudeRunner`
- 위치: 줄 56
- 설명: Claude Code CLI 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools)` (줄 59): 
- `_get_filtered_env(self)` (줄 72): 민감 정보를 제외한 환경 변수 반환
- `_extract_list_run_markup(self, output)` (줄 79): LIST_RUN 마크업에서 리스트 이름 추출
- `_build_command(self, prompt, session_id)` (줄 94): Claude Code CLI 명령어 구성
- `async run(self, prompt, session_id, on_progress)` (줄 121): Claude Code 실행
- `async _execute(self, prompt, session_id)` (줄 140): 실제 실행 로직
- `async _execute_streaming(self, prompt, session_id, on_progress)` (줄 191): 스트리밍 모드 실행 (진행 상황 콜백 호출)
- `_parse_output(self, stdout, stderr)` (줄 348): stream-json 출력 파싱
- `async compact_session(self, session_id)` (줄 427): 세션 컴팩트 처리

## 함수

### `async main()`
- 위치: 줄 462

## 내부 의존성

- `seosoyoung.slackbot.claude.security.SecurityError`
