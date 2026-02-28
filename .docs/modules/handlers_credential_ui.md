# handlers/credential_ui.py

> 경로: `seosoyoung/slackbot/handlers/credential_ui.py`

## 개요

크레덴셜 알림 UI

소울스트림의 credential_alert 이벤트를 슬랙 게이지 바 + 프로필 선택 버튼으로 표시합니다.

## 함수

### `render_gauge(utilization, bar_length)`
- 위치: 줄 32
- 설명: 사용량을 이모지 게이지 바로 렌더링

Args:
    utilization: 사용률 (0.0~1.0) 또는 "unknown"
    bar_length: 게이지 바 길이 (기본 10)

Returns:
    게이지 바 문자열 (예: "🟧🟧🟧🟧🟧🟦🟦🟦🟦🟦")

### `format_time_remaining(resets_at)`
- 위치: 줄 50
- 설명: 리셋까지 남은 시간을 포맷

Args:
    resets_at: 리셋 시간 (ISO 8601) 또는 None

Returns:
    "초기화까지 1시간 15분", "초기화 완료", 또는 ""

### `render_rate_limit_line(rate_type, utilization, resets_at)`
- 위치: 줄 94
- 설명: 단일 rate limit 라인 렌더링

Returns:
    "🟧🟧🟧🟧🟧🟦🟦🟦🟦🟦 5시간: 51% (초기화까지 3일 2시간)"

### `render_profile_section(profile, is_active)`
- 위치: 줄 118
- 설명: 프로필 섹션 렌더링

Args:
    profile: {"name": str, "five_hour": {...}, "seven_day": {...}}
    is_active: 활성 프로필 여부

Returns:
    "*linegames* (활성)\n🟧🟧... 5시간: 95%...\n🟧🟧... 주간: 51%..."

### `build_credential_alert_blocks(active_profile, profiles)`
- 위치: 줄 141
- 설명: 크레덴셜 알림 Block Kit 블록 생성

Args:
    active_profile: 현재 활성 프로필 이름
    profiles: 프로필별 rate limit 정보 리스트

Returns:
    Slack Block Kit blocks

### `build_credential_alert_text(active_profile, profiles)`
- 위치: 줄 196
- 설명: Block Kit의 fallback text

### `send_credential_alert(client, channel, data)`
- 위치: 줄 205
- 설명: 크레덴셜 알림을 슬랙 채널에 전송

Args:
    client: Slack client
    channel: 알림 채널 ID
    data: credential_alert 이벤트 데이터
