# service/claude_runner.py

> 경로: `seosoyoung/soul/service/claude_runner.py`

## 개요

ClaudeCodeRunner - Claude Code CLI 실행

Claude Code SDK를 사용하여 Claude Code를 실행하고 결과를 스트리밍합니다.

## 클래스

### `InterventionMessage`
- 위치: 줄 66
- 설명: 개입 메시지 데이터

### `ClaudeCodeRunner`
- 위치: 줄 73
- 설명: Claude Code CLI 실행기

역할:
1. Claude Code SDK를 사용하여 Claude Code 실행
2. 진행 상황을 SSE 이벤트로 변환
3. 출력 필터링 (비밀 마스킹)
4. 첨부 파일 추출

#### 메서드

- `__init__(self, workspace_dir)` (줄 84): Args:
- `_create_options(self, resume_session_id)` (줄 95): ClaudeCodeOptions 생성
- `_build_intervention_prompt(self, msg)` (줄 120): 개입 메시지를 Claude 프롬프트로 변환
- `_extract_context_usage(self, usage)` (줄 133): ResultMessage.usage에서 컨텍스트 사용량 추출
- `async execute(self, prompt, resume_session_id, get_intervention, on_intervention_sent)` (줄 172): Claude Code 실행 (SSE 이벤트 스트림)

## 내부 의존성

- `seosoyoung.soul.models.CompactEvent`
- `seosoyoung.soul.models.CompleteEvent`
- `seosoyoung.soul.models.ContextUsageEvent`
- `seosoyoung.soul.models.ErrorEvent`
- `seosoyoung.soul.models.InterventionSentEvent`
- `seosoyoung.soul.models.MemoryEvent`
- `seosoyoung.soul.models.ProgressEvent`
- `seosoyoung.soul.service.attachment_extractor.AttachmentExtractor`
- `seosoyoung.soul.service.output_sanitizer.sanitize_output`
- `seosoyoung.soul.service.resource_manager.resource_manager`
- `seosoyoung.soul.service.session_validator.SESSION_NOT_FOUND_CODE`
- `seosoyoung.soul.service.session_validator.validate_session`
