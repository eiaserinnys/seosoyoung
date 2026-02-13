# memory/channel_observer.py

> 경로: `seosoyoung/memory/channel_observer.py`

## 개요

채널 관찰 엔진

채널 버퍼를 읽고 digest를 갱신하며, 반응 판단(none/react/intervene)을 수행합니다.
DigestCompressor는 digest가 임계치를 초과할 때 압축합니다.

## 클래스

### `ChannelObserverResult`
- 위치: 줄 30
- 설명: 채널 관찰 결과 (하위호환 유지)

### `DigestResult`
- 위치: 줄 41
- 설명: 소화 전용 결과

### `JudgeResult`
- 위치: 줄 49
- 설명: 리액션 판단 결과

### `DigestCompressorResult`
- 위치: 줄 59
- 설명: digest 압축 결과

### `ChannelObserver`
- 위치: 줄 145
- 설명: 채널 대화를 관찰하여 digest를 갱신하고 반응을 판단

#### 메서드

- `__init__(self, api_key, model)` (줄 148): 
- `async observe(self, channel_id, existing_digest, channel_messages, thread_buffers)` (줄 152): 채널 버퍼를 분석하여 관찰 결과를 반환합니다 (하위호환).
- `async digest(self, channel_id, existing_digest, judged_messages)` (줄 195): judged 메시지를 digest에 편입합니다 (소화 전용).
- `async judge(self, channel_id, digest, judged_messages, pending_messages)` (줄 242): pending 메시지에 대해 리액션을 판단합니다 (판단 전용).

### `DigestCompressor`
- 위치: 줄 286
- 설명: digest가 임계치를 초과할 때 압축

#### 메서드

- `__init__(self, api_key, model)` (줄 289): 
- `async compress(self, digest, target_tokens)` (줄 294): digest를 압축합니다.

## 함수

### `parse_channel_observer_output(text)`
- 위치: 줄 66
- 설명: Observer 응답에서 XML 태그를 파싱합니다.

### `parse_judge_output(text)`
- 위치: 줄 92
- 설명: Judge 응답에서 XML 태그를 파싱합니다.

### `_parse_reaction(text)`
- 위치: 줄 111
- 설명: XML 텍스트에서 reaction 정보를 추출합니다.

### `_extract_tag(text, tag_name)`
- 위치: 줄 368
- 설명: XML 태그 내용을 추출합니다. 없으면 빈 문자열.

## 내부 의존성

- `seosoyoung.memory.channel_prompts.build_channel_observer_system_prompt`
- `seosoyoung.memory.channel_prompts.build_channel_observer_user_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_compressor_retry_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_compressor_system_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_only_system_prompt`
- `seosoyoung.memory.channel_prompts.build_digest_only_user_prompt`
- `seosoyoung.memory.channel_prompts.build_judge_system_prompt`
- `seosoyoung.memory.channel_prompts.build_judge_user_prompt`
- `seosoyoung.memory.token_counter.TokenCounter`
