# memory/context_builder.py

> 경로: `seosoyoung/memory/context_builder.py`

## 개요

컨텍스트 빌더

장기 기억과 세션 관찰 로그를 시스템 프롬프트로 변환하여 Claude 세션에 주입합니다.
OM의 processInputStep에 해당하는 부분입니다.

주입 계층:
- 장기 기억 (persistent/recent.json): 매 세션 시작 시 항상 주입
- 세션 관찰 (observations/{thread_ts}.json): inject 플래그 있을 때만 주입
- 채널 관찰 (channel/{channel_id}/): 관찰 대상 채널에서 멘션될 때 주입

## 클래스

### `InjectionResult`
- 위치: 줄 31
- 설명: 주입 결과 — 디버그 로그용 정보를 포함

### `ContextBuilder`
- 위치: 줄 221
- 설명: 장기 기억 + 세션 관찰 로그 + 채널 관찰을 시스템 프롬프트로 변환

#### 메서드

- `__init__(self, store, channel_store)` (줄 224): 
- `_build_channel_observation(self, channel_id, thread_ts)` (줄 233): 채널 관찰 컨텍스트를 XML 문자열로 빌드합니다.
- `build_memory_prompt(self, thread_ts, max_tokens, include_persistent, include_session, include_channel_observation, channel_id, include_new_observations)` (줄 285): 장기 기억, 세션 관찰, 채널 관찰, 새 관찰을 합쳐서 시스템 프롬프트로 변환합니다.

## 함수

### `render_observation_items(items, now)`
- 위치: 줄 48
- 설명: 관찰 항목 리스트를 사람이 읽을 수 있는 텍스트로 렌더링합니다.

### `render_persistent_items(items)`
- 위치: 줄 81
- 설명: 장기 기억 항목 리스트를 텍스트로 렌더링합니다.

### `_relative_time_str(date_str, now)`
- 위치: 줄 93
- 설명: 날짜 문자열에 대한 상대 시간 문자열을 반환합니다.

### `optimize_items_for_context(items, max_tokens)`
- 위치: 줄 121
- 설명: 관찰 항목을 컨텍스트 주입에 최적화합니다.

토큰 수 초과 시 오래된 낮은 우선순위 항목부터 제거합니다.

### `add_relative_time(observations, now)`
- 위치: 줄 161
- 설명: [하위 호환] 텍스트 관찰 로그의 날짜 헤더에 상대 시간 주석을 추가합니다.

## [2026-02-10] → ## [2026-02-10] (3일 전)

### `optimize_for_context(observations, max_tokens)`
- 위치: 줄 181
- 설명: [하위 호환] 텍스트 관찰 로그를 컨텍스트 주입에 최적화합니다.

## 내부 의존성

- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
