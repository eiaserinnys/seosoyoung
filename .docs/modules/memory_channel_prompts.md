# memory/channel_prompts.py

> 경로: `seosoyoung/memory/channel_prompts.py`

## 개요

채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.

## 함수

### `build_channel_observer_system_prompt()`
- 위치: 줄 176
- 설명: 채널 관찰 시스템 프롬프트를 반환합니다.

### `build_channel_observer_user_prompt(channel_id, existing_digest, channel_messages, thread_buffers, current_time)`
- 위치: 줄 181
- 설명: 채널 관찰 사용자 프롬프트를 구성합니다.

### `build_digest_compressor_system_prompt(target_tokens)`
- 위치: 줄 214
- 설명: digest 압축 시스템 프롬프트를 반환합니다.

### `build_digest_compressor_retry_prompt(token_count, target_tokens)`
- 위치: 줄 219
- 설명: digest 압축 재시도 프롬프트를 반환합니다.

### `build_intervention_mode_prompt(remaining_turns, channel_id, new_messages, digest)`
- 위치: 줄 228
- 설명: 개입 모드 사용자 프롬프트를 구성합니다.

### `_format_channel_messages(messages)`
- 위치: 줄 251
- 설명: 채널 루트 메시지를 텍스트로 변환

### `_format_thread_messages(thread_buffers)`
- 위치: 줄 264
- 설명: 스레드 메시지를 텍스트로 변환
