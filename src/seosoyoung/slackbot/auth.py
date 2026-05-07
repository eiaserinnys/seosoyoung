"""권한 및 역할 관리

사용자 권한 확인과 역할 조회 기능을 제공합니다.
"""

import logging

from seosoyoung.slackbot.config import Config

logger = logging.getLogger(__name__)


def check_permission(user_id: str, client) -> bool:
    """사용자 권한 확인 (관리자 명령어용)"""
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        allowed = username in Config.auth.allowed_users
        logger.debug(f"권한 체크: user_id={user_id}, username={username}, allowed={allowed}")
        return allowed
    except Exception as e:
        logger.error(f"권한 체크 실패: user_id={user_id}, error={e}")
        return False


def get_user_role(user_id: str, client) -> dict | None:
    """사용자 역할 + 신원 정보 반환.

    `users.info` API 1회 호출로 권한 판정과 caller_info 신원 필드를 함께 채운다
    (정본 하나 원칙 — 분석 캐시 §2). 실패 시 None을 반환하여 호출자가 차단한다.

    Returns:
        dict: 성공 시 다음 키들을 포함
            - user_id: Slack User ID (인자 그대로)
            - username: user.name (소문자 ID, role 판정용)
            - role: "admin" | "viewer"
            - allowed_tools: 역할에 허용된 도구 목록
            - display_name: profile.display_name → real_name 폴백, 둘 다 비면 ""
            - avatar_url: profile.image_192 (없으면 "")
            - email: profile.email (없으면 "")
            - is_bot: 봇 사용자 여부
        실패(SlackApiError, 네트워크, 응답 파싱 실패 등) 시 None.
    """
    try:
        result = client.users_info(user=user_id)
        user = result["user"]
        username = user["name"]
        profile = user.get("profile", {}) or {}
        role = "admin" if username in Config.auth.admin_users else "viewer"
        # display_name 폴백: profile.display_name → profile.real_name → ""
        display_name = (
            profile.get("display_name")
            or profile.get("real_name")
            or ""
        )
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "allowed_tools": Config.auth.role_tools[role],
            "display_name": display_name,
            "avatar_url": profile.get("image_192", ""),
            "email": profile.get("email", ""),
            "is_bot": user.get("is_bot", False),
        }
    except Exception as e:
        logger.error(f"사용자 역할 조회 실패: user_id={user_id}, error={e}")
        return None
