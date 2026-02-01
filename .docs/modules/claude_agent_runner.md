# claude/agent_runner.py

> 경로: `seosoyoung/claude/agent_runner.py`

## 개요

Claude Code SDK 기반 실행기

## 클래스

### `ClaudeResult`
- 위치: 줄 42
- 설명: Claude Code 실행 결과

### `ClaudeAgentRunner`
- 위치: 줄 55
- 설명: Claude Code SDK 기반 실행기

기존 ClaudeRunner(CLI 방식)와 동일한 인터페이스를 제공합니다.

#### 메서드

- `__init__(self, working_dir, timeout, allowed_tools, disallowed_tools, mcp_config_path)` (줄 61): 
- `_build_options(self, session_id)` (줄 76): ClaudeCodeOptions 생성
- `async run(self, prompt, session_id, on_progress)` (줄 104): Claude Code 실행
- `async _execute(self, prompt, session_id, on_progress)` (줄 120): 실제 실행 로직

## 함수

### `async main()`
- 위치: 줄 231
