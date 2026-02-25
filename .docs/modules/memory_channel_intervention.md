# memory/channel_intervention.py

> 경로: `seosoyoung/slackbot/memory/channel_intervention.py`

## 개요

채널 개입(intervention) 모듈

ChannelObserverResult를 InterventionAction으로 변환하고
슬랙 API로 발송하며 개입 이력을 관리합니다.

흐름:
1. parse_intervention_markup: 관찰 결과 → 액션 리스트
2. InterventionHistory.filter_actions: 리액션 필터링
3. execute_interventions: 슬랙 API 발송
4. send_debug_log: 디버그 채널에 로그 전송

## 클래스

### `InterventionAction`
- 위치: 줄 31
- 설명: 개입 액션

### `InterventionHistory`
- 위치: 줄 224
- 설명: 개입 이력 관리

상태 머신 없이, 개입 이력(history 배열)만으로 확률 기반 개입을 지원합니다.

intervention.meta.json 구조:
{
    "history": [
        {"at": 1770974000, "type": "message"},
        {"at": 1770970000, "type": "message"}
    ]
}

#### 메서드

- `__init__(self, base_dir)` (줄 240): 
- `_meta_path(self, channel_id)` (줄 243): 
- `_read_meta(self, channel_id)` (줄 246): 
- `_write_meta(self, channel_id, meta)` (줄 256): 
- `_prune_history(self, history)` (줄 264): 2시간 초과 항목을 제거합니다.
- `record(self, channel_id, entry_type)` (줄 269): 개입 이력을 기록합니다.
- `minutes_since_last(self, channel_id)` (줄 281): 마지막 개입으로부터 경과 시간(분)을 반환합니다.
- `recent_count(self, channel_id, window_minutes)` (줄 295): 최근 window_minutes 내 개입 횟수를 반환합니다.
- `burst_probability(self, channel_id, importance)` (줄 306): 버스트 인식 개입 확률을 반환합니다.
- `can_react(self, channel_id)` (줄 320): 이모지 리액션은 항상 허용
- `filter_actions(self, channel_id, actions)` (줄 324): 액션을 필터링합니다.

## 함수

### `parse_intervention_markup(result)`
- 위치: 줄 39
- 설명: ChannelObserverResult를 InterventionAction 리스트로 변환합니다.

Args:
    result: ChannelObserver의 관찰 결과

Returns:
    실행할 InterventionAction 리스트 (비어있을 수 있음)

### `async execute_interventions(client, channel_id, actions)`
- 위치: 줄 80
- 설명: InterventionAction 리스트를 슬랙 API로 발송합니다.

Args:
    client: Slack WebClient
    channel_id: 대상 채널
    actions: 실행할 액션 리스트

Returns:
    각 액션의 API 응답 (실패 시 None)

### `intervention_probability(minutes_since_last, recent_count)`
- 위치: 줄 132
- 설명: 시간 감쇠와 빈도 감쇠를 기반으로 개입 확률을 계산합니다.

Args:
    minutes_since_last: 마지막 개입으로부터 경과 시간(분)
    recent_count: 최근 2시간 내 개입 횟수

Returns:
    0.0~1.0 사이의 확률 값

### `burst_intervention_probability(history_entries, importance, now)`
- 위치: 줄 154
- 설명: 버스트 인식 개입 확률을 계산합니다.

Args:
    history_entries: 개입 이력 [{"at": timestamp, "type": str}, ...]
    importance: 현재 판단의 중요도 (0-10)
    now: 현재 시각 (테스트용)

Returns:
    0.0~1.0 사이의 확률 값

### `_build_fields_blocks(fields)`
- 위치: 줄 342
- 설명: (label, value) 쌍 리스트를 2열 표 형식의 Block Kit 블록 리스트로 변환합니다.

왼쪽에 항목명(*bold*), 오른쪽에 값이 나오도록 라벨과 값을 별도 field로 배치합니다.
section.fields는 최대 10개이므로, 5쌍(=10 fields)씩 section 블록을 분할합니다.

### `async send_debug_log(client, debug_channel, source_channel, observer_result, actions, actions_filtered, reasoning, emotion, pending_count, reaction_detail)`
- 위치: 줄 361
- 설명: 디버그 채널에 관찰 결과 로그를 전송합니다 (Block Kit 형식).

### `send_collect_debug_log(client, debug_channel, source_channel, buffer_tokens, threshold, message_text, user, is_thread)`
- 위치: 줄 423
- 설명: 메시지 수집 시 디버그 채널에 로그를 전송합니다 (Block Kit 형식).

### `send_digest_skip_debug_log(client, debug_channel, source_channel, buffer_tokens, threshold)`
- 위치: 줄 468
- 설명: 소화 스킵(임계치 미달) 시 디버그 채널에 로그를 전송합니다 (Block Kit 형식).

### `send_intervention_probability_debug_log(client, debug_channel, source_channel, importance, time_factor, freq_factor, probability, final_score, threshold, passed)`
- 위치: 줄 499
- 설명: 확률 기반 개입 판단 결과를 디버그 채널에 기록합니다 (Block Kit 형식).

### `send_multi_judge_debug_log(client, debug_channel, source_channel, items, react_actions, message_actions_executed, pending_count, pending_messages, slack_client)`
- 위치: 줄 544
- 설명: 복수 판단 결과를 메시지별 독립 블록으로 디버그 채널에 전송합니다.

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.memory.channel_observer.ChannelObserverResult`
- `seosoyoung.slackbot.memory.channel_observer.JudgeItem`
- `seosoyoung.slackbot.memory.channel_prompts.DisplayNameResolver`
