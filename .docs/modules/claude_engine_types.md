# claude/engine_types.py

> 경로: `seosoyoung/slackbot/claude/engine_types.py`

## 개요

Claude 엔진 전용 타입 정의

엔진의 순수한 출력·설정 타입만 정의합니다.
슬랙/트렐로/OM 등 응용 계층의 개념을 포함하지 않습니다.

## 클래스

### `EngineResult`
- 위치: 줄 13
- 설명: Claude Code 엔진의 순수 실행 결과

응용 마커(update_requested, restart_requested, list_run)나
OM 전용 필드는 포함하지 않습니다.

### `RoleConfig`
- 위치: 줄 31
- 설명: 역할별 도구 접근 설정

역할 이름("admin", "viewer")은 포함하지 않습니다.
호출자가 역할 이름 → RoleConfig 매핑을 담당합니다.
