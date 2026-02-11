# memory/channel_prompts.py

> 경로: `seosoyoung/memory/channel_prompts.py`

## 개요

채널 관찰 프롬프트

서소영 시점에서 채널 대화를 패시브하게 관찰하여 digest를 갱신하고
반응을 판단하는 프롬프트입니다.

## 함수

### `build_channel_observer_system_prompt()`
- 위치: 줄 135
- 설명: 채널 관찰 시스템 프롬프트를 반환합니다.

### `build_channel_observer_user_prompt(channel_id, existing_digest, channel_messages, thread_buffers, current_time)`
- 위치: 줄 140
- 설명: 채널 관찰 사용자 프롬프트를 구성합니다.

### `build_digest_compressor_system_prompt(target_tokens)`
- 위치: 줄 173
- 설명: digest 압축 시스템 프롬프트를 반환합니다.

### `build_digest_compressor_retry_prompt(token_count, target_tokens)`
- 위치: 줄 178
- 설명: digest 압축 재시도 프롬프트를 반환합니다.

### `_format_channel_messages(messages)`
- 위치: 줄 187
- 설명: 채널 루트 메시지를 텍스트로 변환

### `_format_thread_messages(thread_buffers)`
- 위치: 줄 200
- 설명: 스레드 메시지를 텍스트로 변환
