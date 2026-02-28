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

### `ClaudeResult` (EngineResult)
- 위치: 줄 33
- 설명: Claude Code 실행 결과 (응용 마커 포함)

EngineResult를 상속하며, 응용 마커 필드를 추가합니다.
마커 필드는 executor에서 ParsedMarkers를 통해 설정됩니다.

#### 메서드

- `from_engine_result(cls, result, markers)` (줄 45): EngineResult + markers -> ClaudeResult 변환

### `RoleConfig`
- 위치: 줄 67
- 설명: 역할별 도구 접근 설정

역할 이름("admin", "viewer")은 포함하지 않습니다.
호출자가 역할 이름 → RoleConfig 매핑을 담당합니다.

### `EngineEventType` (Enum)
- 위치: 줄 85
- 설명: 엔진 이벤트 타입

Soul Dashboard가 구독하는 세분화 이벤트 종류.
TEXT_DELTA: AssistantMessage의 TextBlock 텍스트 (모델의 가시적 응답)
TOOL_*: 도구 호출 및 결과
RESULT: 최종 결과 (성공/실패 포함)

Note: SDK의 TextBlock은 assistant의 visible output입니다.
ThinkingBlock(extended thinking)과는 다릅니다.
어댑터 계층(engine_adapter)에서 TEXT_DELTA를
text_start → text_delta → text_end 카드 시퀀스로 변환합니다.

### `EngineEvent`
- 위치: 줄 106
- 설명: 엔진에서 발행하는 단일 이벤트

type: 이벤트 종류 (EngineEventType)
timestamp: 발행 시각 (Unix epoch, float)
data: 이벤트별 페이로드 (dict) — 스키마는 아래 참조
