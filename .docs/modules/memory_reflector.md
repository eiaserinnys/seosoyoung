# memory/reflector.py

> 경로: `seosoyoung/slackbot/memory/reflector.py`

## 개요

Reflector 모듈

관찰 로그가 임계치를 초과할 때 재구조화하고 압축합니다.
OpenAI API를 사용하여 관찰 로그를 요약하고, JSON 형식으로 결과를 파싱합니다.

## 클래스

### `ReflectorResult`
- 위치: 줄 25
- 설명: Reflector 출력 결과

### `Reflector`
- 위치: 줄 93
- 설명: 관찰 로그를 압축하고 재구조화

#### 메서드

- `__init__(self, api_key, model)` (줄 96): 
- `async reflect(self, observations, target_tokens)` (줄 101): 관찰 로그를 압축합니다.

## 함수

### `_parse_reflector_output(text)`
- 위치: 줄 32
- 설명: Reflector 응답 JSON에서 관찰 항목 리스트를 추출합니다.

### `_assign_reflector_ids(raw_items)`
- 위치: 줄 66
- 설명: Reflector가 출력한 항목에 ID를 부여합니다.

## 내부 의존성

- `seosoyoung.memory.prompts.build_reflector_retry_prompt`
- `seosoyoung.memory.prompts.build_reflector_system_prompt`
- `seosoyoung.memory.store.generate_obs_id`
- `seosoyoung.memory.token_counter.TokenCounter`
