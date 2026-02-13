# memory/channel_pipeline.py

> 경로: `seosoyoung/memory/channel_pipeline.py`

## 개요

채널 소화/판단 파이프라인

pending 버퍼에 쌓인 메시지를 기반으로:
1. pending 토큰 확인 → threshold_A 미만이면 스킵
2. judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 digest에 편입)
3. judge() 호출 (digest + judged + pending → 리액션 판단)
4. 리액션 처리 (확률 기반 개입 판단 + 슬랙 발송)
5. pending을 judged로 이동

## 함수

### `_judge_result_to_observer_result(judge, digest)`
- 위치: 줄 43
- 설명: JudgeResult를 ChannelObserverResult로 변환 (하위호환 인터페이스용)

### `_parse_judge_actions(judge_result)`
- 위치: 줄 56
- 설명: JudgeResult에서 InterventionAction 리스트를 생성합니다.

### `async run_channel_pipeline(store, observer, channel_id, slack_client, cooldown, threshold_a, threshold_b, compressor, digest_max_tokens, digest_target_tokens, debug_channel, intervention_threshold, llm_call, claude_runner)`
- 위치: 줄 78
- 설명: 소화/판단 분리 파이프라인을 실행합니다.

흐름:
a) pending 토큰 확인 → threshold_A 미만이면 스킵
b) judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 편입)
c) judge() 호출 (digest + judged + pending)
d) 리액션 처리 (확률 기반 개입 판단 + 슬랙 발송)
e) pending을 judged로 이동

Args:
    store: 채널 데이터 저장소
    observer: ChannelObserver 인스턴스
    channel_id: 대상 채널
    slack_client: Slack WebClient
    cooldown: InterventionHistory 인스턴스
    threshold_a: pending 판단 트리거 토큰 임계치
    threshold_b: digest 편입 트리거 토큰 임계치
    compressor: DigestCompressor (None이면 압축 건너뜀)
    digest_max_tokens: digest 압축 트리거 토큰 임계치
    digest_target_tokens: digest 압축 목표 토큰
    debug_channel: 디버그 로그 채널 (빈 문자열이면 생략)
    intervention_threshold: 확률 기반 개입 임계치 (기본 0.3)
    llm_call: (deprecated) async callable(system_prompt, user_prompt) -> str
    claude_runner: Claude Code SDK 기반 실행기 (우선 사용, 없으면 llm_call 폴백)

### `async _execute_intervene(store, channel_id, slack_client, action, pending_messages, observer_reason, claude_runner, llm_call)`
- 위치: 줄 303
- 설명: 서소영의 개입 응답을 생성하고 발송합니다.

claude_runner가 있으면 Claude Code SDK로, 없으면 llm_call 폴백으로 응답을 생성합니다.

Args:
    store: 채널 데이터 저장소
    channel_id: 대상 채널
    slack_client: Slack WebClient
    action: 실행할 InterventionAction (type="message")
    pending_messages: pending 메시지 (트리거/컨텍스트 분리용)
    observer_reason: judge의 reaction_content (판단 근거/초안)
    claude_runner: Claude Code SDK 기반 실행기 (우선 사용)
    llm_call: (deprecated) async callable(system_prompt, user_prompt) -> str

## 내부 의존성

- `seosoyoung.memory.channel_intervention.InterventionAction`
- `seosoyoung.memory.channel_intervention.InterventionHistory`
- `seosoyoung.memory.channel_intervention.execute_interventions`
- `seosoyoung.memory.channel_intervention.intervention_probability`
- `seosoyoung.memory.channel_intervention.send_debug_log`
- `seosoyoung.memory.channel_intervention.send_intervention_probability_debug_log`
- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_observer.JudgeResult`
- `seosoyoung.memory.channel_prompts.build_channel_intervene_user_prompt`
- `seosoyoung.memory.channel_prompts.get_channel_intervene_system_prompt`
- `seosoyoung.memory.channel_store.ChannelStore`
- `seosoyoung.memory.token_counter.TokenCounter`
