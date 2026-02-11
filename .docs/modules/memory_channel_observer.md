# memory/channel_observer.py

> 경로: `seosoyoung/memory/channel_observer.py`

## 개요

채널 관찰 엔진

채널 버퍼를 읽고 digest를 갱신하며, 반응 판단(none/react/intervene)을 수행합니다.
DigestCompressor는 digest가 임계치를 초과할 때 압축합니다.

## 클래스

### `ChannelObserverResult`
- 위치: 줄 26
- 설명: 채널 관찰 결과

### `DigestCompressorResult`
- 위치: 줄 37
- 설명: digest 압축 결과

### `ChannelObserver`
- 위치: 줄 97
- 설명: 채널 대화를 관찰하여 digest를 갱신하고 반응을 판단

#### 메서드

- `__init__(self, api_key, model)` (줄 100): 
- `async observe(self, channel_id, existing_digest, channel_messages, thread_buffers)` (줄 104): 채널 버퍼를 분석하여 관찰 결과를 반환합니다.

### `DigestCompressor`
- 위치: 줄 148
- 설명: digest가 임계치를 초과할 때 압축

#### 메서드

- `__init__(self, api_key, model)` (줄 151): 
- `async compress(self, digest, target_tokens)` (줄 156): digest를 압축합니다.

## 함수

### `parse_channel_observer_output(text)`
- 위치: 줄 44
- 설명: Observer 응답에서 XML 태그를 파싱합니다.

### `_extract_tag(text, tag_name)`
- 위치: 줄 230
- 설명: XML 태그 내용을 추출합니다. 없으면 빈 문자열.

## 내부 의존성

- `seosoyoung.memory.channel_prompts.build_channel_observer_system_prompt`
- `seosoyoung.memory.channel_prompts.build_channel_observer_user_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_compressor_retry_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_compressor_system_prompt`
- `seosoyoung.memory.token_counter.TokenCounter`
