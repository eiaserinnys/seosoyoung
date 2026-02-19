# memory/observer.py

> 경로: `seosoyoung/memory/observer.py`

## 개요

Observer 모듈

대화 내용을 분석하여 구조화된 관찰 로그를 생성합니다.
OpenAI API를 사용하여 대화를 관찰하고, JSON 형식으로 결과를 파싱합니다.

## 클래스

### `ObserverResult`
- 위치: 줄 24
- 설명: Observer 출력 결과

### `Observer`
- 위치: 줄 145
- 설명: 대화를 관찰하여 구조화된 관찰 로그를 생성

#### 메서드

- `__init__(self, api_key, model)` (줄 148): 
- `async observe(self, existing_observations, messages)` (줄 152): 대화를 관찰하여 새 관찰 로그를 생성합니다.

## 함수

### `parse_observer_output(text, existing_items)`
- 위치: 줄 33
- 설명: Observer 응답 JSON을 파싱합니다.

LLM이 출력한 JSON에서 observations, current_task, suggested_response, candidates를
추출하고, 각 관찰 항목에 ID를 부여합니다.

### `_extract_json(text)`
- 위치: 줄 74
- 설명: 응답 텍스트에서 JSON 객체를 추출합니다.

### `_assign_obs_ids(raw_items, existing)`
- 위치: 줄 98
- 설명: LLM이 출력한 관찰 항목에 ID를 부여합니다.

기존 항목과 동일한 content+priority 조합이면 기존 ID를 유지합니다.
LLM이 id를 반환한 경우 그 ID를 우선 사용합니다.

## 내부 의존성

- `seosoyoung.memory.prompts.build_observer_system_prompt`
- `seosoyoung.memory.prompts.build_observer_user_prompt`
- `seosoyoung.memory.store.generate_obs_id`
