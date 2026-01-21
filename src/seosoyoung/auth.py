"""권한 및 역할 관리

사용자 권한 확인과 역할 조회 기능을 제공합니다.
"""

import logging

from seosoyoung.config import Config

logger = logging.getLogger(__name__)


def check_permission(user_id: str, client) -> bool:
    """사용자 권한 확인 (관리자 명령어용)"""
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        allowed = username in Config.ALLOWED_USERS
        logger.debug(f"권한 체크: user_id={user_id}, username={username}, allowed={allowed}")
        return allowed
    except Exception as e:
        logger.error(f"권한 체크 실패: user_id={user_id}, error={e}")
        return False


def get_user_role(user_id: str, client) -> dict | None:
    """사용자 역할 정보 반환

    Returns:
        dict: {"user_id", "username", "role", "allowed_tools"} 또는 실패 시 None
    """
    try:
        result = client.users_info(user=user_id)
        username = result["user"]["name"]
        role = "admin" if username in Config.ADMIN_USERS else "viewer"
        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "allowed_tools": Config.ROLE_TOOLS[role]
        }
    except Exception as e:
        logger.error(f"사용자 역할 조회 실패: user_id={user_id}, error={e}")
        return None
