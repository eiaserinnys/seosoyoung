"""
Authentication - Bearer 토큰 인증
"""

import os
import secrets
import logging
from fastapi import HTTPException, Header
from typing import Optional

from seosoyoung.soul.config import get_settings


logger = logging.getLogger(__name__)

# 환경변수에서 토큰 읽기
CLAUDE_SERVICE_TOKEN = os.getenv("CLAUDE_SERVICE_TOKEN", "")


async def verify_token(authorization: Optional[str] = Header(None)) -> str:
    """
    Bearer 토큰 검증

    Args:
        authorization: Authorization 헤더 값

    Returns:
        검증된 토큰

    Raises:
        HTTPException: 인증 실패
    """
    settings = get_settings()

    # 토큰이 설정되지 않은 경우
    if not CLAUDE_SERVICE_TOKEN:
        # 프로덕션에서는 토큰 필수
        if settings.is_production:
            logger.error("CLAUDE_SERVICE_TOKEN not configured in production")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "code": "CONFIG_ERROR",
                        "message": "Authentication not configured",
                        "details": {},
                    }
                },
            )
        # 개발 모드에서만 우회 허용
        return ""

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Authorization 헤더가 필요합니다",
                    "details": {},
                }
            },
        )

    # Bearer 토큰 파싱
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Bearer 토큰 형식이 올바르지 않습니다",
                    "details": {},
                }
            },
        )

    token = parts[1]

    # 토큰 검증 (타이밍 공격 방지를 위해 상수 시간 비교 사용)
    if not secrets.compare_digest(token, CLAUDE_SERVICE_TOKEN):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "유효하지 않은 토큰입니다",
                    "details": {},
                }
            },
        )

    return token
