# memory/channel_prompts.py

> 경로: `seosoyoung/memory/channel_prompts.py`

## 개요

채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.

프롬프트 텍스트는 prompt_files/ 디렉토리의 외부 파일에서 로드됩니다.

## 함수

### `_load(filename)`
- 위치: 줄 14
- 설명: 내부 헬퍼: 캐시된 프롬프트 로드

### `build_channel_observer_system_prompt()`
- 위치: 줄 19
- 설명: 채널 관찰 시스템 프롬프트를 반환합니다.

### `build_channel_observer_user_prompt(channel_id, existing_digest, channel_messages, thread_buffers, current_time)`
- 위치: 줄 24
- 설명: 채널 관찰 사용자 프롬프트를 구성합니다.

### `build_digest_compressor_system_prompt(target_tokens)`
- 위치: 줄 58
- 설명: digest 압축 시스템 프롬프트를 반환합니다.

### `build_digest_compressor_retry_prompt(token_count, target_tokens)`
- 위치: 줄 63
- 설명: digest 압축 재시도 프롬프트를 반환합니다.

### `get_channel_intervene_system_prompt()`
- 위치: 줄 72
- 설명: 채널 개입 응답 생성 시스템 프롬프트를 반환합니다.

### `build_channel_intervene_user_prompt(digest, recent_messages, trigger_message, target, observer_reason)`
- 위치: 줄 77
- 설명: 채널 개입 응답 생성 사용자 프롬프트를 구성합니다.

### `build_digest_only_system_prompt()`
- 위치: 줄 108
- 설명: 소화 전용 시스템 프롬프트를 반환합니다.

### `build_digest_only_user_prompt(channel_id, existing_digest, judged_messages, current_time)`
- 위치: 줄 113
- 설명: 소화 전용 사용자 프롬프트를 구성합니다.

### `build_judge_system_prompt()`
- 위치: 줄 144
- 설명: 리액션 판단 전용 시스템 프롬프트를 반환합니다.

### `build_judge_user_prompt(channel_id, digest, judged_messages, pending_messages, thread_buffers, bot_user_id)`
- 위치: 줄 149
- 설명: 리액션 판단 전용 사용자 프롬프트를 구성합니다.

### `_format_pending_messages(messages, bot_user_id)`
- 위치: 줄 175
- 설명: pending 메시지를 텍스트로 변환.

사람이 보낸 봇 멘션 메시지는 멘션 핸들러가 처리하므로 [ALREADY REACTED] 표기.
봇이 보낸 멘션은 채널 모니터가 처리해야 하므로 태그하지 않음.

### `_format_channel_messages(messages)`
- 위치: 줄 199
- 설명: 채널 루트 메시지를 텍스트로 변환

### `_format_thread_messages(thread_buffers)`
- 위치: 줄 212
- 설명: 스레드 메시지를 텍스트로 변환

## 내부 의존성

- `seosoyoung.memory.prompt_loader.load_prompt_cached`
