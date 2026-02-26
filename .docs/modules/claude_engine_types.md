# claude/engine_types.py

> 경로: `seosoyoung/slackbot/claude/engine_types.py`

## 개요

Claude 엔진 전용 타입 정의

엔진의 순수한 출력·설정 타입만 정의합니다.
슬랙/트렐로/OM 등 응용 계층의 개념을 포함하지 않습니다.

## 클래스

### `EngineResult`
- 위치: 줄 15
- 설명: Claude Code 엔진의 순수 실행 결과

응용 마커(update_requested, restart_requested, list_run)나
OM 전용 필드는 포함하지 않습니다.

### `RoleConfig`
- 위치: 줄 33
- 설명: 역할별 도구 접근 설정

역할 이름("admin", "viewer")은 포함하지 않습니다.
호출자가 역할 이름 → RoleConfig 매핑을 담당합니다.

### `EngineEventType` (Enum)
- 위치: 줄 51
- 설명: 엔진 이벤트 타입

Soul Dashboard가 구독하는 세분화 이벤트 종류.
THINKING_*: 모델 사고 스트림
TOOL_*: 도구 호출 및 결과
RESULT: 최종 결과 (성공/실패 포함)
STATE_CHANGE: 엔진 상태 전환 (idle → running 등)

### `EngineEvent`
- 위치: 줄 71
- 설명: 엔진에서 발행하는 단일 이벤트

type: 이벤트 종류
timestamp: 발행 시각 (Unix epoch, float)
data: 이벤트별 페이로드 (dict)
  - THINKING_DELTA: {"text": str}
  - TOOL_START: {"tool_name": str, "tool_input": dict}
  - TOOL_RESULT: {"tool_name": str, "result": Any}
  - RESULT: {"success": bool, "output": str, "error": Optional[str]}
  - STATE_CHANGE: {"from_state": str, "to_state": str}
