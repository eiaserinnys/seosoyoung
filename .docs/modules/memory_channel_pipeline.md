# memory/channel_pipeline.py

> 경로: `seosoyoung/memory/channel_pipeline.py`

## 개요

채널 소화/판단 파이프라인

pending 버퍼에 쌓인 메시지를 기반으로:
1. pending 토큰 확인 → threshold_A 미만이면 스킵
2. judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 digest에 편입)
3. judge() 호출 (digest + judged + pending → 메시지별 리액션 판단)
4. 리액션 처리 (이모지 일괄 + 확률 기반 개입 판단 + 슬랙 발송)
5. pending을 judged로 이동

## 함수

### `_judge_result_to_observer_result(judge, digest)`
- 위치: 줄 45
- 설명: JudgeResult를 ChannelObserverResult로 변환 (하위호환 인터페이스용)

### `_parse_judge_item_action(item)`
- 위치: 줄 58
- 설명: JudgeItem에서 InterventionAction을 생성합니다. 반응이 없으면 None.

### `_parse_judge_actions(judge_result)`
- 위치: 줄 80
- 설명: JudgeResult에서 InterventionAction 리스트를 생성합니다.

items가 있으면 각 JudgeItem에서 액션을 추출합니다.
없으면 하위호환 단일 필드에서 추출합니다.

### `_apply_importance_modifiers(judge_result, pending_messages)`
- 위치: 줄 115
- 설명: related_to_me 가중치와 addressed_to_me 강제 반응을 적용합니다.

- related_to_me == True → importance × 2 (상한 10)
- addressed_to_me == True && 발신자가 사람 → importance 최소 7, intervene 전환

### `_validate_linked_messages(judge_result, judged_messages, pending_messages)`
- 위치: 줄 148
- 설명: linked_message_ts가 실제 존재하는 ts인지 검증하고, 환각된 ts를 제거합니다.

자기 자신을 가리키는 링크도 제거합니다.

### `_get_max_importance_item(judge_result)`
- 위치: 줄 179
- 설명: JudgeResult에서 가장 높은 중요도의 JudgeItem을 반환합니다.

### `_filter_already_reacted(actions, pending_messages, bot_user_id)`
- 위치: 줄 186
- 설명: 봇이 이미 리액션한 메시지에 대한 react 액션을 필터링합니다.

pending_messages의 reactions 필드에 봇이 같은 이모지로 이미 리액션한 경우 스킵합니다.

Args:
    actions: react 타입 InterventionAction 리스트
    pending_messages: pending 메시지 리스트 (reactions 필드 포함 가능)
    bot_user_id: 봇의 사용자 ID

Returns:
    중복이 아닌 액션만 남긴 리스트

### `async run_channel_pipeline(store, observer, channel_id, slack_client, cooldown, threshold_a, threshold_b, compressor, digest_max_tokens, digest_target_tokens, debug_channel, intervention_threshold, llm_call, claude_runner, bot_user_id)`
- 위치: 줄 230
- 설명: 소화/판단 분리 파이프라인을 실행합니다.

흐름:
a) pending 토큰 확인 → threshold_A 미만이면 스킵
b) judged + pending 합산 > threshold_B이면 → digest() 호출 (judged를 편입)
c) judge() 호출 (digest + judged + pending → 메시지별 판단)
d) 리액션 처리 (이모지 일괄 + 확률 기반 개입 판단 + 슬랙 발송)
e) pending을 judged로 이동

### `async _handle_multi_judge(judge_result, store, channel_id, slack_client, cooldown, pending_messages, current_digest, debug_channel, intervention_threshold, llm_call, claude_runner, bot_user_id, session_manager, thread_buffers)`
- 위치: 줄 403
- 설명: 복수 JudgeItem 처리: 이모지 일괄 + 개입 확률 판단

### `async _handle_single_judge(judge_result, store, channel_id, slack_client, cooldown, pending_messages, current_digest, debug_channel, intervention_threshold, llm_call, claude_runner, bot_user_id, session_manager, thread_buffers)`
- 위치: 줄 510
- 설명: 하위호환: 단일 JudgeResult 처리

### `async _execute_intervene(store, channel_id, slack_client, action, pending_messages, observer_reason, claude_runner, llm_call, bot_user_id, session_manager, thread_buffers)`
- 위치: 줄 635
- 설명: 서소영의 개입 응답을 생성하고 발송합니다.

### `_remove_thinking_reaction(client, channel_id, ts)`
- 위치: 줄 771
- 설명: 트리거 메시지에서 :ssy-thinking: 이모지를 제거합니다.

### `_swap_thinking_to_happy(client, channel_id, ts)`
- 위치: 줄 781
- 설명: :ssy-thinking: 이모지를 :ssy-happy:로 교체합니다.

## 내부 의존성

- `seosoyoung.memory.channel_intervention.InterventionAction`
- `seosoyoung.memory.channel_intervention.InterventionHistory`
- `seosoyoung.memory.channel_intervention.execute_interventions`
- `seosoyoung.memory.channel_intervention.intervention_probability`
- `seosoyoung.memory.channel_intervention.send_debug_log`
- `seosoyoung.memory.channel_intervention.send_intervention_probability_debug_log`
- `seosoyoung.memory.channel_intervention.send_multi_judge_debug_log`
- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_observer.JudgeItem`
- `seosoyoung.memory.channel_observer.JudgeResult`
- `seosoyoung.memory.channel_prompts.build_channel_intervene_user_prompt`
- `seosoyoung.memory.channel_prompts.get_channel_intervene_system_prompt`
- `seosoyoung.memory.channel_store.ChannelStore`
- `seosoyoung.memory.token_counter.TokenCounter`
