# service/session_validator.py

> 경로: `seosoyoung/soul/service/session_validator.py`

## 개요

세션 검증 모듈

Claude Code 세션의 유효성을 검증하고 세션 파일을 찾습니다.

## 함수

### `find_session_file(session_id)`
- 위치: 줄 16
- 설명: 세션 파일을 찾습니다.

세션 파일은 ~/.claude/projects/{project-path}/{session-id}.jsonl 형식으로 저장됩니다.
여러 프로젝트 경로에서 검색합니다.

Args:
    session_id: 세션 ID (UUID 형식)

Returns:
    세션 파일 경로 또는 None

### `validate_session(session_id)`
- 위치: 줄 44
- 설명: 세션 ID가 유효한지 검증합니다.

검증 항목:
1. UUID 형식이 올바른지
2. 세션 파일이 존재하는지

Args:
    session_id: 세션 ID

Returns:
    에러 메시지 (유효하면 None)
