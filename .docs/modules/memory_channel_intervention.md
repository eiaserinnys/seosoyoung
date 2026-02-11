# memory/channel_intervention.py

> 경로: `seosoyoung/memory/channel_intervention.py`

## 개요

채널 개입(intervention) 모듈

Phase 3: ChannelObserverResult를 InterventionAction으로 변환하고
슬랙 API로 발송하며 쿨다운을 관리합니다.

흐름:
1. parse_intervention_markup: 관찰 결과 → 액션 리스트
2. CooldownManager.filter_actions: 쿨다운 필터링
3. execute_interventions: 슬랙 API 발송
4. send_debug_log: 디버그 채널에 로그 전송

## 클래스

### `InterventionAction`
- 위치: 줄 26
- 설명: 개입 액션

### `CooldownManager`
- 위치: 줄 127
- 설명: 개입 쿨다운 관리

대화 개입(message)은 쿨다운 대상, 이모지 리액션(react)은 제외.
마지막 개입 시각을 intervention.meta.json에 기록합니다.

#### 메서드

- `__init__(self, base_dir, cooldown_sec)` (줄 134): 
- `_meta_path(self, channel_id)` (줄 138): 
- `_read_meta(self, channel_id)` (줄 141): 
- `_write_meta(self, channel_id, meta)` (줄 147): 
- `can_intervene(self, channel_id)` (줄 155): 대화 개입이 가능한지 확인 (쿨다운 체크)
- `can_react(self, channel_id)` (줄 163): 이모지 리액션은 항상 허용
- `record_intervention(self, channel_id)` (줄 167): 개입 시각을 기록
- `filter_actions(self, channel_id, actions)` (줄 173): 쿨다운에 따라 액션을 필터링합니다.

## 함수

### `parse_intervention_markup(result)`
- 위치: 줄 34
- 설명: ChannelObserverResult를 InterventionAction 리스트로 변환합니다.

Args:
    result: ChannelObserver의 관찰 결과

Returns:
    실행할 InterventionAction 리스트 (비어있을 수 있음)

### `async execute_interventions(client, channel_id, actions)`
- 위치: 줄 75
- 설명: InterventionAction 리스트를 슬랙 API로 발송합니다.

Args:
    client: Slack WebClient
    channel_id: 대상 채널
    actions: 실행할 액션 리스트

Returns:
    각 액션의 API 응답 (실패 시 None)

### `async send_debug_log(client, debug_channel, source_channel, observer_result, actions, actions_filtered)`
- 위치: 줄 198
- 설명: 디버그 채널에 관찰 결과 로그를 전송합니다.

Args:
    client: Slack WebClient
    debug_channel: 디버그 로그 채널 ID
    source_channel: 관찰한 원본 채널 ID
    observer_result: 관찰 결과
    actions: 파싱된 전체 액션 리스트
    actions_filtered: 쿨다운 필터 후 실제 실행된 액션 리스트

## 내부 의존성

- `seosoyoung.memory.channel_observer.ChannelObserverResult`
