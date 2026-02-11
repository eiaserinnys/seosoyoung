# memory/channel_pipeline.py

> 경로: `seosoyoung/memory/channel_pipeline.py`

## 개요

채널 소화 파이프라인

버퍼에 쌓인 채널 메시지를 ChannelObserver로 소화하여 digest를 갱신하고,
필요 시 DigestCompressor로 압축합니다.

흐름:
1. count_buffer_tokens() 체크 → 임계치 미만이면 스킵
2. 기존 digest + 버퍼 로드
3. ChannelObserver.observe() 호출
4. 새 digest 저장 + 버퍼 비우기
5. digest 토큰이 max_tokens 초과 시 DigestCompressor 호출
6. 반응 마크업 반환 (Phase 3에서 슬랙봇이 처리)

## 함수

### `async digest_channel(store, observer, channel_id, buffer_threshold, compressor, digest_max_tokens, digest_target_tokens)`
- 위치: 줄 30
- 설명: 채널 버퍼를 소화하여 digest를 갱신합니다.

Args:
    store: 채널 데이터 저장소
    observer: ChannelObserver 인스턴스
    channel_id: 소화할 채널 ID
    buffer_threshold: 소화 트리거 토큰 임계치
    compressor: DigestCompressor (None이면 압축 건너뜀)
    digest_max_tokens: digest 압축 트리거 토큰 임계치
    digest_target_tokens: digest 압축 목표 토큰

Returns:
    ChannelObserverResult (반응 정보 포함) 또는 None (스킵/실패)

## 내부 의존성

- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_store.ChannelStore`
- `seosoyoung.memory.token_counter.TokenCounter`
