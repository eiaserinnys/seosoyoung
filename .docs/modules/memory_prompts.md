# memory/prompts.py

> 경로: `seosoyoung/slackbot/plugins/memory/prompts.py`

## 개요

Observer/Reflector 프롬프트

Mastra의 Observational Memory 프롬프트를 서소영 컨텍스트에 맞게 조정한 프롬프트입니다.

프롬프트 텍스트는 prompt_files/ 디렉토리의 외부 파일에서 로드됩니다.

## 함수

### `_load(filename)`
- 위치: 줄 14
- 설명: 내부 헬퍼: 캐시된 프롬프트 로드

### `build_observer_system_prompt()`
- 위치: 줄 19
- 설명: Observer 시스템 프롬프트를 반환합니다.

### `build_observer_user_prompt(existing_observations, messages, current_time)`
- 위치: 줄 24
- 설명: Observer 사용자 프롬프트를 구성합니다.

### `_format_messages(messages)`
- 위치: 줄 55
- 설명: 메시지 목록을 Observer 입력용 텍스트로 변환

### `build_reflector_system_prompt()`
- 위치: 줄 67
- 설명: Reflector 시스템 프롬프트를 반환합니다.

### `build_reflector_retry_prompt(token_count, target)`
- 위치: 줄 72
- 설명: Reflector 재시도 프롬프트를 반환합니다.

### `build_promoter_prompt(existing_persistent, candidate_entries)`
- 위치: 줄 79
- 설명: Promoter 프롬프트를 구성합니다.

### `build_compactor_prompt(persistent_memory, target_tokens)`
- 위치: 줄 100
- 설명: Compactor 프롬프트를 구성합니다.

## 내부 의존성

- `seosoyoung.slackbot.plugins.memory.prompt_loader.load_prompt_cached`
