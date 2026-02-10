# memory/observer.py

> 경로: `seosoyoung/memory/observer.py`

## 개요

Observer 모듈

대화 내용을 분석하여 구조화된 관찰 로그를 생성합니다.
OpenAI API를 사용하여 대화를 관찰하고, XML 태그 형식으로 결과를 파싱합니다.

## 클래스

### `ObserverResult`
- 위치: 줄 22
- 설명: Observer 출력 결과

### `Observer`
- 위치: 줄 60
- 설명: 대화를 관찰하여 구조화된 관찰 로그를 생성

#### 메서드

- `__init__(self, api_key, model)` (줄 63): 
- `async observe(self, existing_observations, messages)` (줄 67): 대화를 관찰하여 새 관찰 로그를 생성합니다.

## 함수

### `parse_observer_output(text)`
- 위치: 줄 30
- 설명: Observer 응답에서 XML 태그를 파싱합니다.

<observations>, <current-task>, <suggested-response> 태그를 추출합니다.
태그가 없는 경우 전체 응답을 observations로 사용합니다 (fallback).

### `_extract_tag(text, tag_name)`
- 위치: 줄 51
- 설명: XML 태그 내용을 추출합니다. 없으면 빈 문자열.

## 내부 의존성

- `seosoyoung.memory.prompts.build_observer_system_prompt`
- `seosoyoung.memory.prompts.build_observer_user_prompt`
