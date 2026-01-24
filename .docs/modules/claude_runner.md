# claude/runner.py

> 경로: `seosoyoung/claude/runner.py`

## 개요

Claude Code CLI 래퍼

## 클래스

### `ClaudeResult`
- 위치: 줄 43
- 설명: Claude Code 실행 결과

### `ClaudeRunner`
- 위치: 줄 55
- 설명: Claude Code CLI 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools)` (줄 58): 
- `_get_filtered_env(self)` (줄 71): 민감 정보를 제외한 환경 변수 반환
- `_build_command(self, prompt, session_id)` (줄 78): Claude Code CLI 명령어 구성
- `async run(self, prompt, session_id, on_progress)` (줄 105): Claude Code 실행
- `async _execute(self, prompt, session_id)` (줄 124): 실제 실행 로직
- `async _execute_streaming(self, prompt, session_id, on_progress)` (줄 175): 스트리밍 모드 실행 (진행 상황 콜백 호출)
- `_parse_output(self, stdout, stderr)` (줄 326): stream-json 출력 파싱
- `async compact_session(self, session_id)` (줄 399): 세션 컴팩트 처리

## 함수

### `async main()`
- 위치: 줄 434

## 내부 의존성

- `seosoyoung.claude.security.SecurityError`
