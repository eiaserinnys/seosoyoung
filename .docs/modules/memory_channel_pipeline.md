# memory/channel_pipeline.py

> 경로: `seosoyoung/memory/channel_pipeline.py`

## 개요

채널 소화 파이프라인

버퍼에 쌓인 채널 메시지를 ChannelObserver로 소화하여 digest를 갱신하고,
필요 시 DigestCompressor로 압축합니다.
소화 결과에 개입 액션이 있으면 쿨다운 필터 후 슬랙으로 발송합니다.

흐름:
1. count_buffer_tokens() 체크 → 임계치 미만이면 스킵
2. 기존 digest + 버퍼 로드
3. ChannelObserver.observe() 호출
4. 새 digest 저장 + 버퍼 비우기
5. digest 토큰이 max_tokens 초과 시 DigestCompressor 호출
6. 반응 마크업 → InterventionAction 변환 → 쿨다운 필터 → 슬랙 발송

## 함수

### `async digest_channel(store, observer, channel_id, buffer_threshold, compressor, digest_max_tokens, digest_target_tokens)`
- 위치: 줄 42
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

### `async run_digest_and_intervene(store, observer, channel_id, slack_client, cooldown, buffer_threshold, compressor, digest_max_tokens, digest_target_tokens, debug_channel, max_intervention_turns)`
- 위치: 줄 152
- 설명: 소화 파이프라인 + 개입 실행을 일괄 수행합니다.

message handler에서 별도 스레드로 호출합니다.

Args:
    store: 채널 데이터 저장소
    observer: ChannelObserver 인스턴스
    channel_id: 대상 채널
    slack_client: Slack WebClient
    cooldown: CooldownManager 인스턴스
    buffer_threshold: 소화 트리거 토큰 임계치
    compressor: DigestCompressor (None이면 압축 건너뜀)
    digest_max_tokens: digest 압축 트리거 토큰 임계치
    digest_target_tokens: digest 압축 목표 토큰
    debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
    max_intervention_turns: 개입 모드 최대 턴 (0이면 개입 모드 비활성)

### `async respond_in_intervention_mode(store, channel_id, slack_client, cooldown, llm_call)`
- 위치: 줄 234
- 설명: 개입 모드 중 새 메시지에 반응합니다.

버퍼에 쌓인 메시지를 읽고, LLM으로 서소영의 응답을 생성하여
슬랙에 발송하고, 턴을 소모합니다.

Args:
    store: 채널 데이터 저장소
    channel_id: 대상 채널
    slack_client: Slack WebClient
    cooldown: CooldownManager 인스턴스
    llm_call: async callable(system_prompt, user_prompt) -> str

## 내부 의존성

- `seosoyoung.memory.channel_intervention.CooldownManager`
- `seosoyoung.memory.channel_intervention.InterventionAction`
- `seosoyoung.memory.channel_intervention.execute_interventions`
- `seosoyoung.memory.channel_intervention.parse_intervention_markup`
- `seosoyoung.memory.channel_intervention.send_debug_log`
- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_prompts.INTERVENTION_MODE_SYSTEM_PROMPT`
- `seosoyoung.memory.channel_prompts.build_intervention_mode_prompt`
- `seosoyoung.memory.channel_store.ChannelStore`
- `seosoyoung.memory.token_counter.TokenCounter`
