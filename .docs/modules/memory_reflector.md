# memory/reflector.py

> 경로: `seosoyoung/memory/reflector.py`

## 개요

Reflector 모듈

관찰 로그가 임계치를 초과할 때 재구조화하고 압축합니다.
OpenAI API를 사용하여 관찰 로그를 요약하고, XML 태그 형식으로 결과를 파싱합니다.

## 클래스

### `ReflectorResult`
- 위치: 줄 23
- 설명: Reflector 출력 결과

### `Reflector`
- 위치: 줄 38
- 설명: 관찰 로그를 압축하고 재구조화

#### 메서드

- `__init__(self, api_key, model)` (줄 41): 
- `async reflect(self, observations, target_tokens)` (줄 46): 관찰 로그를 압축합니다.

## 함수

### `_extract_observations(text)`
- 위치: 줄 30
- 설명: 응답에서 <observations> 태그 내용을 추출합니다. 없으면 전체 텍스트.

## 내부 의존성

- `seosoyoung.memory.prompts.build_reflector_retry_prompt`
- `seosoyoung.memory.prompts.build_reflector_system_prompt`
- `seosoyoung.memory.token_counter.TokenCounter`
