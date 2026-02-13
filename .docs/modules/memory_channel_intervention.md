# memory/channel_intervention.py

> 경로: `seosoyoung/memory/channel_intervention.py`

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
- 위치: 줄 29
- 설명: 개입 액션

### `InterventionHistory`
- 위치: 줄 152
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

- `__init__(self, base_dir)` (줄 168): 
- `_meta_path(self, channel_id)` (줄 171): 
- `_read_meta(self, channel_id)` (줄 174): 
- `_write_meta(self, channel_id, meta)` (줄 184): 
- `_prune_history(self, history)` (줄 192): 2시간 초과 항목을 제거합니다.
- `record(self, channel_id, entry_type)` (줄 197): 개입 이력을 기록합니다.
- `minutes_since_last(self, channel_id)` (줄 209): 마지막 개입으로부터 경과 시간(분)을 반환합니다.
- `recent_count(self, channel_id, window_minutes)` (줄 223): 최근 window_minutes 내 개입 횟수를 반환합니다.
- `can_react(self, channel_id)` (줄 234): 이모지 리액션은 항상 허용
- `filter_actions(self, channel_id, actions)` (줄 238): 액션을 필터링합니다.

## 함수

### `parse_intervention_markup(result)`
- 위치: 줄 37
- 설명: ChannelObserverResult를 InterventionAction 리스트로 변환합니다.

Args:
    result: ChannelObserver의 관찰 결과

Returns:
    실행할 InterventionAction 리스트 (비어있을 수 있음)

### `async execute_interventions(client, channel_id, actions)`
- 위치: 줄 78
- 설명: InterventionAction 리스트를 슬랙 API로 발송합니다.

Args:
    client: Slack WebClient
    channel_id: 대상 채널
    actions: 실행할 액션 리스트

Returns:
    각 액션의 API 응답 (실패 시 None)

### `intervention_probability(minutes_since_last, recent_count)`
- 위치: 줄 130
- 설명: 시간 감쇠와 빈도 감쇠를 기반으로 개입 확률을 계산합니다.

Args:
    minutes_since_last: 마지막 개입으로부터 경과 시간(분)
    recent_count: 최근 2시간 내 개입 횟수

Returns:
    0.0~1.0 사이의 확률 값

### `async send_debug_log(client, debug_channel, source_channel, observer_result, actions, actions_filtered)`
- 위치: 줄 256
- 설명: 디버그 채널에 관찰 결과 로그를 전송합니다.

Args:
    client: Slack WebClient
    debug_channel: 디버그 로그 채널 ID
    source_channel: 관찰한 원본 채널 ID
    observer_result: 관찰 결과
    actions: 파싱된 전체 액션 리스트
    actions_filtered: 쿨다운 필터 후 실제 실행된 액션 리스트

### `send_collect_debug_log(client, debug_channel, source_channel, buffer_tokens, threshold, message_text, user, is_thread)`
- 위치: 줄 296
- 설명: 메시지 수집 시 디버그 채널에 로그를 전송합니다.

Args:
    client: Slack WebClient
    debug_channel: 디버그 로그 채널 ID
    source_channel: 관찰 대상 채널 ID
    buffer_tokens: 현재 버퍼 토큰 수
    threshold: 소화 트리거 임계치
    message_text: 수집된 메시지 텍스트
    user: 메시지 작성자
    is_thread: 스레드 메시지 여부

### `send_digest_skip_debug_log(client, debug_channel, source_channel, buffer_tokens, threshold)`
- 위치: 줄 342
- 설명: 소화 스킵(임계치 미달) 시 디버그 채널에 로그를 전송합니다.

### `send_intervention_probability_debug_log(client, debug_channel, source_channel, importance, time_factor, freq_factor, probability, final_score, threshold, passed)`
- 위치: 줄 364
- 설명: 확률 기반 개입 판단 결과를 디버그 채널에 기록합니다.

Args:
    client: Slack WebClient
    debug_channel: 디버그 로그 채널 ID
    source_channel: 관찰 대상 채널 ID
    importance: judge 중요도 (0-10)
    time_factor: 시간 감쇠 요소
    freq_factor: 빈도 감쇠 요소
    probability: intervention_probability 결과
    final_score: 최종 점수 (importance/10 × probability)
    threshold: 개입 임계치
    passed: 임계치 통과 여부

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.memory.channel_observer.ChannelObserverResult`
