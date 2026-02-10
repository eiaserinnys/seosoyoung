# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 78
- 설명: Claude Code 실행 결과

### `ClaudeAgentRunner`
- 위치: 줄 93
- 설명: Claude Code SDK 기반 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools, mcp_config_path)` (줄 96): 
- `_build_options(self, session_id, compact_events, user_id)` (줄 111): ClaudeCodeOptions 생성
- `async run(self, prompt, session_id, on_progress, on_compact, user_id)` (줄 183): Claude Code 실행
- `async _execute(self, prompt, session_id, on_progress, on_compact, user_id)` (줄 203): 실제 실행 로직
- `async compact_session(self, session_id)` (줄 353): 세션 컴팩트 처리

## 함수

### `_classify_process_error(e)`
- 위치: 줄 24
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.

### `async main()`
- 위치: 줄 383
