# memory/observation_pipeline.py

> 경로: `seosoyoung/memory/observation_pipeline.py`

## 개요

관찰 파이프라인

매턴마다 Observer를 호출하여 세션 관찰 로그를 갱신하고, 장기 기억 후보를 수집합니다.

흐름:
1. 이번 턴 대화의 토큰을 계산 → 최소 토큰(min_turn_tokens) 미만이면 스킵
2. Observer 호출 (매턴) → 세션 관찰 로그 갱신
3. <candidates> 태그가 있으면 장기 기억 후보 버퍼에 적재
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축

## 함수

### `_send_debug_log(channel, text)`
- 위치: 줄 25
- 설명: OM 디버그 로그를 슬랙 채널에 발송. 메시지 ts를 반환.

### `_update_debug_log(channel, ts, text)`
- 위치: 줄 39
- 설명: 기존 디버그 로그 메시지를 수정

### `_format_tokens(n)`
- 위치: 줄 53
- 설명: 토큰 수를 천 단위 콤마 포맷

### `_short_ts(thread_ts)`
- 위치: 줄 58
- 설명: thread_ts를 짧은 식별자로 변환. 예: 1234567890.123456 → ...3456

### `parse_candidate_entries(candidates_text)`
- 위치: 줄 65
- 설명: <candidates> 태그 내용을 파싱하여 dict 리스트로 변환.

각 줄에서 이모지 우선순위(🔴🟡🟢)와 내용을 추출합니다.

### `async observe_conversation(store, observer, thread_ts, user_id, messages, min_turn_tokens, reflector, reflection_threshold, debug_channel)`
- 위치: 줄 101
- 설명: 매턴 Observer를 호출하여 세션 관찰 로그를 갱신하고 후보를 수집합니다.

Args:
    store: 관찰 로그 저장소
    observer: Observer 인스턴스
    thread_ts: 세션(스레드) 타임스탬프 — 저장 키
    user_id: 사용자 ID — 메타데이터용
    messages: 이번 턴 대화 내역
    min_turn_tokens: 최소 턴 토큰 (이하 스킵)
    reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
    reflection_threshold: Reflector 트리거 토큰 임계치
    debug_channel: 디버그 로그를 발송할 슬랙 채널

Returns:
    True: 관찰 수행됨, False: 스킵 또는 실패

## 내부 의존성

- `seosoyoung.memory.observer.Observer`
- `seosoyoung.memory.reflector.Reflector`
- `seosoyoung.memory.store.MemoryRecord`
- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
