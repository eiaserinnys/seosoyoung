# service/engine_adapter.py

> 경로: `seosoyoung/soul/service/engine_adapter.py`

## 개요

soul 엔진 어댑터

slackbot.claude.agent_runner의 ClaudeRunner를 soul API용으로 래핑합니다.
ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환하여
기존 soul 스트리밍 인터페이스와 호환합니다.

## 클래스

### `_CardTracker`
- 위치: 줄 55
- 설명: SSE 이벤트용 카드 ID 관리 + text↔tool 관계 추적

AssistantMessage의 TextBlock 하나를 '카드'로 추상화합니다.
카드 ID는 UUID4 기반 8자리 식별자로 생성됩니다.

SDK는 TextBlock을 청크 스트리밍하지 않으므로 TEXT_DELTA 하나가
하나의 완전한 카드에 해당합니다.

#### 메서드

- `__init__(self)` (줄 65): 
- `new_card(self)` (줄 69): 새 카드 ID 생성 및 현재 카드로 설정
- `current_card_id(self)` (줄 79): 현재 활성 카드 ID (thinking 블록 없이 tool이 오면 None)
- `set_last_tool(self, tool_name)` (줄 83): 마지막 도구 이름 기록 (TOOL_RESULT에서 tool_name 폴백용)
- `last_tool(self)` (줄 88): 마지막으로 호출된 도구 이름

### `InterventionMessage`
- 위치: 줄 94
- 설명: 개입 메시지 데이터

### `SoulEngineAdapter`
- 위치: 줄 141
- 설명: ClaudeRunner -> AsyncIterator[SSE Event] 어댑터

ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환합니다.
기존 soul의 ClaudeCodeRunner.execute()와 동일한 인터페이스를 제공합니다.

#### 메서드

- `__init__(self, workspace_dir, pool)` (줄 149): 
- `_resolve_mcp_config_path(self)` (줄 157): WORKSPACE_DIR 기준으로 mcp_config.json 경로를 해석
- `async execute(self, prompt, resume_session_id, get_intervention, on_intervention_sent)` (줄 164): Claude Code 실행 (SSE 이벤트 스트림)

## 함수

### `_extract_context_usage(usage)`
- 위치: 줄 101
- 설명: EngineResult.usage에서 컨텍스트 사용량 이벤트 생성

### `_build_intervention_prompt(msg)`
- 위치: 줄 128
- 설명: 개입 메시지를 Claude 프롬프트로 변환

### `init_soul_engine(pool)`
- 위치: 줄 396
- 설명: soul_engine 싱글톤을 (재)초기화한다.

lifespan에서 풀 생성 후 호출하여 싱글톤을 교체한다.

Args:
    pool: 주입할 ClaudeRunnerPool. None이면 풀 없이 초기화.

Returns:
    새로 생성된 SoulEngineAdapter 인스턴스

## 내부 의존성

- `seosoyoung.slackbot.claude.agent_runner.ClaudeRunner`
- `seosoyoung.slackbot.claude.engine_types.EngineEvent`
- `seosoyoung.slackbot.claude.engine_types.EngineEventType`
- `seosoyoung.soul.config.get_settings`
- `seosoyoung.soul.models.CompactEvent`
- `seosoyoung.soul.models.CompleteEvent`
- `seosoyoung.soul.models.ContextUsageEvent`
- `seosoyoung.soul.models.DebugEvent`
- `seosoyoung.soul.models.ErrorEvent`
- `seosoyoung.soul.models.InterventionSentEvent`
- `seosoyoung.soul.models.ProgressEvent`
- `seosoyoung.soul.models.ResultSSEEvent`
- `seosoyoung.soul.models.SessionEvent`
- `seosoyoung.soul.models.TextDeltaSSEEvent`
- `seosoyoung.soul.models.TextEndSSEEvent`
- `seosoyoung.soul.models.TextStartSSEEvent`
- `seosoyoung.soul.models.ToolResultSSEEvent`
- `seosoyoung.soul.models.ToolStartSSEEvent`
