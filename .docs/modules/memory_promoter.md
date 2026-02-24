# memory/promoter.py

> 경로: `seosoyoung/slackbot/memory/promoter.py`

## 개요

Promoter / Compactor 모듈

장기 기억 후보를 검토하여 승격(Promoter)하고,
장기 기억이 임계치를 넘으면 압축(Compactor)합니다.

## 클래스

### `PromoterResult`
- 위치: 줄 22
- 설명: Promoter 출력 결과

#### 메서드

- `__post_init__(self)` (줄 31): 

### `CompactorResult`
- 위치: 줄 37
- 설명: Compactor 출력 결과

### `Promoter`
- 위치: 줄 181
- 설명: 장기 기억 후보를 검토하여 승격

#### 메서드

- `__init__(self, api_key, model)` (줄 184): 
- `async promote(self, candidates, existing_persistent)` (줄 188): 후보 항목들을 검토하여 장기 기억 승격 여부를 판단합니다.
- `merge_promoted(existing, promoted)` (줄 214): 승격된 항목을 기존 장기 기억에 머지합니다. ID 기반 중복 제거.

### `Compactor`
- 위치: 줄 233
- 설명: 장기 기억을 압축

#### 메서드

- `__init__(self, api_key, model)` (줄 236): 
- `async compact(self, persistent, target_tokens)` (줄 241): 장기 기억을 압축합니다.

## 함수

### `_extract_json(text)`
- 위치: 줄 44
- 설명: 응답 텍스트에서 JSON을 추출합니다.

### `_assign_ltm_ids(raw_items, existing)`
- 위치: 줄 74
- 설명: LTM 항목에 ID를 부여합니다.

기존 항목과 content+priority가 일치하면 기존 ID를 유지합니다.
LLM이 id를 반환한 경우 그 ID를 우선 사용합니다.

### `parse_promoter_output(text, existing_items)`
- 위치: 줄 119
- 설명: Promoter 응답 JSON에서 promoted와 rejected를 파싱합니다.

### `parse_compactor_output(text, existing_items)`
- 위치: 줄 159
- 설명: Compactor 응답에서 JSON 배열을 파싱합니다.

## 내부 의존성

- `seosoyoung.memory.prompts.build_compactor_prompt`
- `seosoyoung.memory.prompts.build_promoter_prompt`
- `seosoyoung.memory.store.generate_ltm_id`
- `seosoyoung.memory.token_counter.TokenCounter`
