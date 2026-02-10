# memory/observation_pipeline.py

> 경로: `seosoyoung/memory/observation_pipeline.py`

## 개요

관찰 파이프라인

세션 종료 시 대화를 버퍼에 누적하고, 누적 토큰이 임계치를 넘으면 Observer를 트리거합니다.
Mastra의 원본 구현처럼 상한선(threshold) 기반으로 동작합니다.

흐름:
1. 세션 대화를 세션(thread_ts)별 pending 버퍼에 append
2. pending 토큰 합산 → 임계치 미만이면 저장만 하고 종료
3. 임계치 이상이면 Observer 호출 → 관찰 로그 갱신 → pending 비우기
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

### `_progress_bar(current, total, width)`
- 위치: 줄 58
- 설명: 프로그레스 바 생성. 예: ■■■■□□□□□□

### `_short_ts(thread_ts)`
- 위치: 줄 66
- 설명: thread_ts를 짧은 식별자로 변환. 예: 1234567890.123456 → ...3456

### `async observe_conversation(store, observer, thread_ts, user_id, messages, observation_threshold, reflector, reflection_threshold, debug_channel)`
- 위치: 줄 73
- 설명: 대화를 버퍼에 누적하고, 임계치 도달 시 관찰합니다.

Args:
    store: 관찰 로그 저장소
    observer: Observer 인스턴스
    thread_ts: 세션(스레드) 타임스탬프 — 저장 키
    user_id: 사용자 ID — 메타데이터용
    messages: 이번 세션 대화 내역
    observation_threshold: Observer 트리거 토큰 임계치
    reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
    reflection_threshold: Reflector 트리거 토큰 임계치
    debug_channel: 디버그 로그를 발송할 슬랙 채널

Returns:
    True: 관찰 수행됨, False: 버퍼에 누적만 함 또는 실패

### `_make_observation_diff(old, new)`
- 위치: 줄 225
- 설명: 관찰 로그의 변경점을 간략히 표시.

새로 추가된 줄에 + 접두사, 삭제된 줄에 - 접두사를 붙입니다.
너무 길면 truncate합니다.

## 내부 의존성

- `seosoyoung.memory.observer.Observer`
- `seosoyoung.memory.reflector.Reflector`
- `seosoyoung.memory.store.MemoryRecord`
- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
