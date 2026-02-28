# service/rate_limit_tracker.py

> 경로: `seosoyoung/soul/service/rate_limit_tracker.py`

## 개요

RateLimitTracker - 프로필별 rate limit 상태 추적 모듈

프로필별 five_hour/seven_day rate limit utilization을 추적하고,
95% 임계값 도달 시 알림을 트리거합니다.
상태는 JSON 파일로 영속화되어 재시작 시 복원됩니다.

저장 경로: {profiles_dir}/_rate_limits.json

## 클래스

### `RateLimitTracker`
- 위치: 줄 59
- 설명: 프로필별 rate limit 상태 추적기.

Args:
    profiles_dir: 프로필 저장 디렉토리 (영속화 파일 위치)

#### 메서드

- `__init__(self, profiles_dir)` (줄 66): 
- `_load(self)` (줄 78): 영속화 파일에서 상태 복원.
- `save(self)` (줄 91): 현재 상태를 JSON 파일로 영속화.
- `record(self, profile, rate_limit_type, utilization, resets_at)` (줄 108): rate limit 이벤트 기록.
- `get_profile_state(self, profile)` (줄 169): 특정 프로필의 rate limit 상태 조회.
- `get_all_states(self)` (줄 206): 모든 프로필의 rate limit 상태 조회.
- `build_credential_alert(self, active_profile)` (줄 220): credential_alert SSE 이벤트 데이터 생성.

## 함수

### `_now_utc()`
- 위치: 줄 30
- 설명: 현재 UTC 시간.

### `_parse_iso(iso_str)`
- 위치: 줄 35
- 설명: ISO 8601 문자열을 datetime으로 파싱.

None이거나 파싱 실패 시 None 반환.

### `_is_expired(resets_at)`
- 위치: 줄 48
- 설명: resets_at 시간이 경과했는지 확인.

None이면 만료되지 않은 것으로 처리.
