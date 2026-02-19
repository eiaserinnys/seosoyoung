# memory/channel_scheduler.py

> 경로: `seosoyoung/memory/channel_scheduler.py`

## 개요

채널 소화 주기적 스케줄러

버퍼에 메시지가 쌓여 있지만 임계치에 도달하지 못한 경우,
일정 주기(기본 5분)마다 소화 파이프라인을 트리거합니다.

## 클래스

### `ChannelDigestScheduler`
- 위치: 줄 18
- 설명: 주기적으로 채널 버퍼를 체크하여 소화를 트리거하는 스케줄러

threading.Timer를 사용하여 interval_sec 간격으로 실행합니다.
버퍼에 토큰이 1개 이상 있으면 소화 파이프라인을 실행합니다.
(buffer_threshold=1로 호출하여 임계치 무관하게 동작)

#### 메서드

- `__init__(self)` (줄 26): 
- `start(self)` (줄 61): 스케줄러를 시작합니다.
- `stop(self)` (줄 72): 스케줄러를 중지합니다.
- `_schedule_next(self)` (줄 80): 다음 실행을 예약합니다.
- `_tick(self)` (줄 88): 주기적 실행: 각 채널의 버퍼를 체크하고 소화를 트리거합니다.
- `_check_and_digest(self)` (줄 97): 모든 관찰 채널의 pending 버퍼를 체크하여 파이프라인을 트리거합니다.
- `_run_pipeline(self, channel_id)` (줄 119): 소화/판단 파이프라인을 실행합니다.

## 내부 의존성

- `seosoyoung.memory.channel_intervention.InterventionHistory`
- `seosoyoung.memory.channel_observer.ChannelObserver`
- `seosoyoung.memory.channel_observer.DigestCompressor`
- `seosoyoung.memory.channel_store.ChannelStore`
