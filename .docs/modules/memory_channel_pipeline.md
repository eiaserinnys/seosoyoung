# memory/channel_pipeline.py

> 경로: `seosoyoung/memory/channel_pipeline.py`

## 개요

채널 소화/판단 파이프라인

pending 버퍼에 쌓인 메시지를 기반으로:
1. pending 토큰 확인 → threshold_A 미만이면 스킵
2. judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 digest에 편입)
3. judge() 호출 (digest + judged + pending → 리액션 판단)
4. 리액션 처리 (슬랙 발송)
5. pending을 judged로 이동

## 함수

### `_judge_result_to_observer_result(judge, digest)`
- 위치: 줄 40
- 설명: JudgeResult를 ChannelObserverResult로 변환 (하위호환 인터페이스용)

### `_parse_judge_actions(judge_result)`
- 위치: 줄 53
- 설명: JudgeResult에서 InterventionAction 리스트를 생성합니다.

### `async run_channel_pipeline(store, observer, channel_id, slack_client, cooldown, threshold_a, threshold_b, compressor, digest_max_tokens, digest_target_tokens, debug_channel, max_intervention_turns, llm_call)`
- 위치: 줄 75
- 설명: 소화/판단 분리 파이프라인을 실행합니다.

흐름:
a) pending 토큰 확인 → threshold_A 미만이면 스킵
b) judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 편입)
c) judge() 호출 (digest + judged + pending)
d) 리액션 처리 (기존 intervention 로직 재활용)
e) pending을 judged로 이동

Args:
    store: 채널 데이터 저장소
    observer: ChannelObserver 인스턴스
    channel_id: 대상 채널
    slack_client: Slack WebClient
    cooldown: CooldownManager 인스턴스
    threshold_a: pending 판단 트리거 토큰 임계치
    threshold_b: digest 편입 트리거 토큰 임계치
    compressor: DigestCompressor (None이면 압축 건너뜀)
    digest_max_tokens: digest 압축 트리거 토큰 임계치
    digest_target_tokens: digest 압축 목표 토큰
    debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
    max_intervention_turns: 개입 모드 최대 턴 (0이면 개입 모드 비활성)
    llm_call: async callable(system_prompt, user_prompt) -> str

### `async _execute_intervene_with_llm(store, channel_id, slack_client, llm_call, action, pending_messages, observer_reason)`
- 위치: 줄 283
- 설명: LLM을 호출하여 서소영의 개입 응답을 생성하고 발송합니다.

Args:
    store: 채널 데이터 저장소
    channel_id: 대상 채널
    slack_client: Slack WebClient
    llm_call: async callable(system_prompt, user_prompt) -> str
    action: 실행할 InterventionAction (type="message")
    pending_messages: pending 메시지 (트리거/컨텍스트 분리용)
    observer_reason: judge의 reaction_content (판단 근거/초안)

### `async respond_in_intervention_mode(store, channel_id, slack_client, cooldown, llm_call, debug_channel)`
- 위치: 줄 365
- 설명: 개입 모드 중 새 메시지에 반응합니다.

버퍼에 쌓인 메시지를 읽고, LLM으로 서소영의 응답을 생성하여
슬랙에 발송하고, 턴을 소모합니다.

Args:
    store: 채널 데이터 저장소
    channel_id: 대상 채널
    slack_client: Slack WebClient
    cooldown: CooldownManager 인스턴스
    llm_call: async callable(system_prompt, user_prompt) -> str
    debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)

## 내부 의존성

- `seosoyoung.memory.channel_intervention.CooldownManager`
- `seosoyoung.memory.channel_intervention.InterventionAction`
- `seosoyoung.memory.channel_intervention.execute_interventions`
- `seosoyoung.memory.channel_intervention.send_debug_log`
- `seosoyoung.memory.channel_intervention.send_intervention_mode_debug_log`
- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_observer.JudgeResult`
- `seosoyoung.memory.channel_prompts.build_channel_intervene_user_prompt`
- `seosoyoung.memory.channel_prompts.build_intervention_mode_prompt`
- `seosoyoung.memory.channel_prompts.get_channel_intervene_system_prompt`
- `seosoyoung.memory.channel_prompts.get_intervention_mode_system_prompt`
- `seosoyoung.memory.channel_store.ChannelStore`
- `seosoyoung.memory.token_counter.TokenCounter`
