# memory/context_builder.py

> 경로: `seosoyoung/memory/context_builder.py`

## 개요

컨텍스트 빌더

관찰 로그를 시스템 프롬프트로 변환하여 Claude 세션에 주입합니다.
OM의 processInputStep에 해당하는 부분입니다.

## 클래스

### `ContextBuilder`
- 위치: 줄 102
- 설명: 관찰 로그를 시스템 프롬프트로 변환

#### 메서드

- `__init__(self, store)` (줄 105): 
- `build_memory_prompt(self, thread_ts, max_tokens)` (줄 108): 세션의 관찰 로그를 시스템 프롬프트로 변환합니다.

## 함수

### `add_relative_time(observations, now)`
- 위치: 줄 17
- 설명: 관찰 로그의 날짜 헤더에 상대 시간 주석을 추가합니다.

## [2026-02-10] → ## [2026-02-10] (3일 전)

### `optimize_for_context(observations, max_tokens)`
- 위치: 줄 60
- 설명: 관찰 로그를 컨텍스트 주입에 최적화합니다.

- 토큰 수 초과 시 truncate (오래된 내용부터 제거)

## 내부 의존성

- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
