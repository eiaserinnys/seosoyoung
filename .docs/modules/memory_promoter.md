# memory/promoter.py

> 경로: `seosoyoung/memory/promoter.py`

## 개요

Promoter / Compactor 모듈

장기 기억 후보를 검토하여 승격(Promoter)하고,
장기 기억이 임계치를 넘으면 압축(Compactor)합니다.

## 클래스

### `PromoterResult`
- 위치: 줄 20
- 설명: Promoter 출력 결과

#### 메서드

- `__post_init__(self)` (줄 29): 

### `CompactorResult`
- 위치: 줄 35
- 설명: Compactor 출력 결과

### `Promoter`
- 위치: 줄 103
- 설명: 장기 기억 후보를 검토하여 승격

#### 메서드

- `__init__(self, api_key, model)` (줄 106): 
- `async promote(self, candidates, existing_persistent)` (줄 110): 후보 항목들을 검토하여 장기 기억 승격 여부를 판단합니다.
- `_format_candidates(candidates)` (줄 137): 후보 항목을 프롬프트용 텍스트로 포매팅.
- `merge_promoted(existing, promoted)` (줄 148): 승격된 항목을 기존 장기 기억에 머지합니다.

### `Compactor`
- 위치: 줄 157
- 설명: 장기 기억을 압축

#### 메서드

- `__init__(self, api_key, model)` (줄 160): 
- `async compact(self, persistent, target_tokens)` (줄 165): 장기 기억을 압축합니다.

## 함수

### `_extract_tag(text, tag_name)`
- 위치: 줄 42
- 설명: XML 태그 내용을 추출합니다. 없으면 빈 문자열.

### `_count_entries(text)`
- 위치: 줄 51
- 설명: 이모지 프리픽스(🔴🟡🟢) 또는 '-' 로 시작하는 비어있지 않은 줄 수를 카운트.

### `_count_priority(text)`
- 위치: 줄 67
- 설명: 승격 텍스트에서 우선순위별 카운트를 추출.

### `parse_promoter_output(text)`
- 위치: 줄 83
- 설명: Promoter 응답에서 <promoted>와 <rejected> 태그를 파싱합니다.

### `parse_compactor_output(text)`
- 위치: 줄 97
- 설명: Compactor 응답에서 <compacted> 태그를 파싱합니다.

## 내부 의존성

- `seosoyoung.memory.prompts.build_compactor_prompt`
- `seosoyoung.memory.prompts.build_promoter_prompt`
- `seosoyoung.memory.token_counter.TokenCounter`
