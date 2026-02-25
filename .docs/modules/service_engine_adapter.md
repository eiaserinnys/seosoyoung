# service/engine_adapter.py

> 경로: `seosoyoung/soul/service/engine_adapter.py`

## 개요

soul 엔진 어댑터

slackbot.claude.agent_runner의 ClaudeRunner를 soul API용으로 래핑합니다.
ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환하여
기존 soul 스트리밍 인터페이스와 호환합니다.

## 클래스

### `InterventionMessage`
- 위치: 줄 48
- 설명: 개입 메시지 데이터

### `SoulEngineAdapter`
- 위치: 줄 95
- 설명: ClaudeRunner -> AsyncIterator[SSE Event] 어댑터

ClaudeRunner.run()의 콜백(on_progress, on_compact, on_intervention)을
asyncio.Queue를 통해 SSE 이벤트 스트림으로 변환합니다.
기존 soul의 ClaudeCodeRunner.execute()와 동일한 인터페이스를 제공합니다.

#### 메서드

- `__init__(self, workspace_dir, pool)` (줄 103): 
- `_resolve_mcp_config_path(self)` (줄 111): WORKSPACE_DIR 기준으로 mcp_config.json 경로를 해석
- `async execute(self, prompt, resume_session_id, get_intervention, on_intervention_sent)` (줄 118): Claude Code 실행 (SSE 이벤트 스트림)

## 함수

### `_extract_context_usage(usage)`
- 위치: 줄 55
- 설명: EngineResult.usage에서 컨텍스트 사용량 이벤트 생성

### `_build_intervention_prompt(msg)`
- 위치: 줄 82
- 설명: 개입 메시지를 Claude 프롬프트로 변환

### `init_soul_engine(pool)`
- 위치: 줄 291
- 설명: soul_engine 싱글톤을 (재)초기화한다.

lifespan에서 풀 생성 후 호출하여 싱글톤을 교체한다.

Args:
    pool: 주입할 ClaudeRunnerPool. None이면 풀 없이 초기화.

Returns:
    새로 생성된 SoulEngineAdapter 인스턴스

## 내부 의존성

- `seosoyoung.slackbot.claude.agent_runner.ClaudeRunner`
- `seosoyoung.soul.config.get_settings`
- `seosoyoung.soul.models.CompactEvent`
- `seosoyoung.soul.models.CompleteEvent`
- `seosoyoung.soul.models.ContextUsageEvent`
- `seosoyoung.soul.models.DebugEvent`
- `seosoyoung.soul.models.ErrorEvent`
- `seosoyoung.soul.models.InterventionSentEvent`
- `seosoyoung.soul.models.ProgressEvent`
- `seosoyoung.soul.models.SessionEvent`
