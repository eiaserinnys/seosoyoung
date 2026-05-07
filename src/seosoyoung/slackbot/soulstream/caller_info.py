"""Slack caller_info 조립 헬퍼

슬랙 채널/유저/스레드 컨텍스트로부터 soul-server /execute 요청에 실릴
caller_info 딕셔너리를 조립합니다.

스키마는 soul-server 쪽 Task.caller_info 컬럼과 호환됩니다 (통합 v1 스키마).
soul-server /execute가 request body에 caller_info가 있으면 HTTP Request에서
수집하지 않고 이 값을 그대로 사용합니다.

통합 스키마 v1 (분석 캐시 §2):
- top-level: source, user_id, [display_name, avatar_url, email], slack, bot_name
- slack sub-dict: channel_id, user_id, [thread_ts]
- top-level user_id ↔ slack.user_id는 동일값 의도적 중복 (push notifier·표시 호환)
- 신원 필드(display_name 등)는 비면 키 자체가 들어가지 않음 (graceful)
"""

from typing import Optional


BOT_NAME = "seosoyoung"


def build_slack_caller_info(
    channel_id: str,
    user_id: str,
    thread_ts: Optional[str] = None,
    *,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    email: Optional[str] = None,
) -> dict:
    """슬랙 호출 맥락으로부터 caller_info 딕셔너리를 조립합니다.

    Args:
        channel_id: 슬랙 채널 ID
        user_id: 호출한 슬랙 사용자 ID
        thread_ts: 스레드 타임스탬프 (없으면 None)
        display_name: 발신자 표시명 (profile.display_name → real_name 폴백 후 호출자가 채움)
        avatar_url: 발신자 프로필 이미지 URL (profile.image_192 권장)
        email: 발신자 이메일 (profile.email)

    Returns:
        soul-server /execute 요청의 caller_info 필드에 실릴 딕셔너리.
        {
            "source": "slack",
            "user_id": "U...",                        # top-level (의도적 중복)
            "display_name": "서소영",                 # 있을 때만
            "avatar_url": "https://...",              # 있을 때만
            "email": "...",                           # 있을 때만
            "slack": {
                "channel_id": "C...",
                "user_id": "U...",                    # = top-level user_id
                "thread_ts": "...",                   # None/빈 값이면 생략
            },
            "bot_name": "seosoyoung",
        }
    """
    slack: dict = {
        "channel_id": channel_id,
        "user_id": user_id,
    }
    if thread_ts:
        slack["thread_ts"] = thread_ts

    info: dict = {
        "source": "slack",
        "user_id": user_id,
        "slack": slack,
        "bot_name": BOT_NAME,
    }
    # 신원 필드는 비면 키 자체를 넣지 않는다 (graceful — 부분 성공 케이스)
    if display_name:
        info["display_name"] = display_name
    if avatar_url:
        info["avatar_url"] = avatar_url
    if email:
        info["email"] = email

    return info
