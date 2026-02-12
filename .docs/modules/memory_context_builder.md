# memory/context_builder.py

> 경로: `seosoyoung/memory/context_builder.py`

## 개요

컨텍스트 빌더

장기 기억과 세션 관찰 로그를 시스템 프롬프트로 변환하여 Claude 세션에 주입합니다.
OM의 processInputStep에 해당하는 부분입니다.

주입 계층:
- 장기 기억 (persistent/recent.md): 매 세션 시작 시 항상 주입
- 세션 관찰 (observations/{thread_ts}.md): inject 플래그 있을 때만 주입
- 채널 관찰 (channel/{channel_id}/): 관찰 대상 채널에서 멘션될 때 주입

## 클래스

### `InjectionResult`
- 위치: 줄 31
- 설명: 주입 결과 — 디버그 로그용 정보를 포함

### `ContextBuilder`
- 위치: 줄 130
- 설명: 장기 기억 + 세션 관찰 로그 + 채널 관찰을 시스템 프롬프트로 변환

#### 메서드

- `__init__(self, store, channel_store)` (줄 133): 
- `_build_channel_observation(self, channel_id, thread_ts)` (줄 142): 채널 관찰 컨텍스트를 XML 문자열로 빌드합니다.
- `build_memory_prompt(self, thread_ts, max_tokens, include_persistent, include_session, include_channel_observation, channel_id, include_new_observations)` (줄 192): 장기 기억, 세션 관찰, 채널 관찰, 새 관찰을 합쳐서 시스템 프롬프트로 변환합니다.

## 함수

### `add_relative_time(observations, now)`
- 위치: 줄 45
- 설명: 관찰 로그의 날짜 헤더에 상대 시간 주석을 추가합니다.

## [2026-02-10] → ## [2026-02-10] (3일 전)

### `optimize_for_context(observations, max_tokens)`
- 위치: 줄 88
- 설명: 관찰 로그를 컨텍스트 주입에 최적화합니다.

- 토큰 수 초과 시 truncate (오래된 내용부터 제거)

## 내부 의존성

- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
