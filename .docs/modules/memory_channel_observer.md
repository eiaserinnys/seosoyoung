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

### `JudgeItem`
- 위치: 줄 49
- 설명: 개별 메시지에 대한 리액션 판단 결과

### `JudgeResult`
- 위치: 줄 66
- 설명: 복수 메시지에 대한 리액션 판단 결과

items가 있으면 메시지별 개별 판단 결과를 사용합니다.
items가 없으면 하위호환용 단일 필드를 사용합니다.

### `DigestCompressorResult`
- 위치: 줄 89
- 설명: digest 압축 결과

### `ChannelObserver`
- 위치: 줄 247
- 설명: 채널 대화를 관찰하여 digest를 갱신하고 반응을 판단

#### 메서드

- `__init__(self, api_key, model)` (줄 250): 
- `async observe(self, channel_id, existing_digest, channel_messages, thread_buffers)` (줄 254): 채널 버퍼를 분석하여 관찰 결과를 반환합니다 (하위호환).
- `async digest(self, channel_id, existing_digest, judged_messages)` (줄 297): judged 메시지를 digest에 편입합니다 (소화 전용).
- `async judge(self, channel_id, digest, judged_messages, pending_messages, thread_buffers, bot_user_id)` (줄 344): pending 메시지에 대해 리액션을 판단합니다 (판단 전용).

### `DigestCompressor`
- 위치: 줄 394
- 설명: digest가 임계치를 초과할 때 압축

#### 메서드

- `__init__(self, api_key, model)` (줄 397): 
- `async compress(self, digest, target_tokens)` (줄 402): digest를 압축합니다.

## 함수

### `parse_channel_observer_output(text)`
- 위치: 줄 96
- 설명: Observer 응답에서 XML 태그를 파싱합니다.

### `parse_judge_output(text)`
- 위치: 줄 122
- 설명: Judge 응답에서 XML 태그를 파싱합니다.

복수 <judgment ts="..."> 블록이 있으면 각각을 JudgeItem으로 파싱합니다.
없으면 하위호환으로 단일 결과를 파싱합니다.

### `_parse_yes_no(text, tag_name)`
- 위치: 줄 173
- 설명: yes/no 태그를 파싱합니다. 없거나 'no'면 False.

### `_parse_judge_item(ts, block)`
- 위치: 줄 179
- 설명: 개별 <judgment> 블록을 JudgeItem으로 파싱합니다.

### `_parse_reaction(text)`
- 위치: 줄 213
- 설명: XML 텍스트에서 reaction 정보를 추출합니다.

### `_extract_tag(text, tag_name)`
- 위치: 줄 476
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
