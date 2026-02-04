# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 41
- 설명: Claude Code 실행 결과

### `ClaudeAgentRunner`
- 위치: 줄 54
- 설명: Claude Code SDK 기반 실행기

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools, mcp_config_path)` (줄 57): 
- `_build_options(self, session_id)` (줄 72): ClaudeCodeOptions 생성
- `async run(self, prompt, session_id, on_progress)` (줄 100): Claude Code 실행
- `async _execute(self, prompt, session_id, on_progress)` (줄 116): 실제 실행 로직
- `async compact_session(self, session_id)` (줄 225): 세션 컴팩트 처리

## 함수

### `async main()`
- 위치: 줄 255
