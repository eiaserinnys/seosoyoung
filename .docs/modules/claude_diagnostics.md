# claude/diagnostics.py

> 경로: `seosoyoung/rescue/claude/diagnostics.py`

## 개요

세션 진단 및 에러 분류 로직

agent_runner.py에서 분리된 진단 전용 모듈.
ProcessError 분류, 세션 덤프 생성, stderr 캡처 등을 담당합니다.

## 함수

### `read_stderr_tail(n_lines)`
- 위치: 줄 24
- 설명: 세션별 cli_stderr 로그의 마지막 N줄 읽기

### `build_session_dump()`
- 위치: 줄 47
- 설명: 세션 종료 진단 덤프 메시지 생성

### `classify_process_error(e)`
- 위치: 줄 87
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

### `format_rate_limit_warning(rate_limit_info)`
- 위치: 줄 117
- 설명: allowed_warning용 사람이 읽을 수 있는 안내문 생성.
