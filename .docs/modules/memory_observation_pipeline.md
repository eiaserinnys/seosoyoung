# memory/observation_pipeline.py

> 경로: `seosoyoung/memory/observation_pipeline.py`

## 개요

관찰 파이프라인

세션 종료 시 대화를 관찰하고 관찰 로그를 갱신하는 파이프라인입니다.
agent_runner의 Stop 훅에서 비동기로 트리거됩니다.

## 함수

### `_send_debug_log(channel, text)`
- 위치: 줄 19
- 설명: OM 디버그 로그를 슬랙 채널에 발송

### `async observe_conversation(store, observer, user_id, messages, min_conversation_tokens, reflector, reflection_threshold, debug_channel)`
- 위치: 줄 31
- 설명: 대화를 관찰하고 관찰 로그를 갱신합니다.

Args:
    store: 관찰 로그 저장소
    observer: Observer 인스턴스
    user_id: 사용자 ID
    messages: 세션 대화 내역
    min_conversation_tokens: 최소 대화 토큰 수
    reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
    reflection_threshold: Reflector 트리거 토큰 임계치
    debug_channel: 디버그 로그를 발송할 슬랙 채널 (빈 문자열이면 발송 안 함)

Returns:
    True: 관찰 성공, False: 관찰 건너뜀 또는 실패

## 내부 의존성

- `seosoyoung.memory.observer.Observer`
- `seosoyoung.memory.reflector.Reflector`
- `seosoyoung.memory.store.MemoryRecord`
- `seosoyoung.memory.store.MemoryStore`
- `seosoyoung.memory.token_counter.TokenCounter`
