"""Slack caller_info 조립 헬퍼

슬랙 채널/유저/스레드 컨텍스트로부터 soul-server /execute 요청에 실릴
caller_info 딕셔너리를 조립합니다.

스키마는 soul-server 쪽 Task.caller_info 컬럼과 호환됩니다 (Phase 1).
soul-server /execute가 request body에 caller_info가 있으면 HTTP Request에서
수집하지 않고 이 값을 그대로 사용합니다 (Phase 2).
"""

from typing import Optional


BOT_NAME = "seosoyoung"


def build_slack_caller_info(
    channel_id: str,
    user_id: str,
    thread_ts: Optional[str] = None,
) -> dict:
    """슬랙 호출 맥락으로부터 caller_info 딕셔너리를 조립합니다.

    Args:
        channel_id: 슬랙 채널 ID
        user_id: 호출한 슬랙 사용자 ID
        thread_ts: 스레드 타임스탬프 (없으면 None)

    Returns:
        soul-server /execute 요청의 caller_info 필드에 실릴 딕셔너리.
        {
            "source": "slack",
            "slack": {
                "channel_id": ...,
                "user_id": ...,
                "thread_ts": ...,  # None 이면 생략
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

    return {
        "source": "slack",
        "slack": slack,
        "bot_name": BOT_NAME,
    }
