"""
Credentials API - 프로필 관리 REST 엔드포인트

프로필 목록 조회, 활성 프로필 확인, 저장/활성화/삭제, rate limit 현황.
모든 엔드포인트는 Bearer 토큰 인증이 필요합니다.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from seosoyoung.soul.api.auth import verify_token
from seosoyoung.soul.service.credential_store import CredentialStore
from seosoyoung.soul.service.credential_swapper import CredentialSwapper
from seosoyoung.soul.service.rate_limit_tracker import RateLimitTracker

logger = logging.getLogger(__name__)


def create_credentials_router(
    store: CredentialStore,
    swapper: CredentialSwapper,
    rate_limit_tracker: Optional[RateLimitTracker] = None,
) -> APIRouter:
    """
    Credentials API 라우터 팩토리.

    Args:
        store: 프로필 저장소
        swapper: 크레덴셜 교체기
        rate_limit_tracker: rate limit 추적기 (None이면 rate-limits 엔드포인트 비활성)

    Returns:
        FastAPI APIRouter
    """
    router = APIRouter()

    @router.get("")
    async def list_profiles(_: str = Depends(verify_token)):
        """
        GET /profiles — 프로필 목록 + 메타데이터
        """
        profiles = store.list_profiles()
        active = store.get_active()
        return {"profiles": profiles, "active": active}

    @router.get("/active")
    async def get_active_profile(_: str = Depends(verify_token)):
        """
        GET /profiles/active — 현재 활성 프로필 정보
        """
        active = store.get_active()
        if active is None:
            return {"active": None, "profile": None}

        profiles = store.list_profiles()
        profile_meta = next(
            (p for p in profiles if p["name"] == active), None
        )
        return {"active": active, "profile": profile_meta}

    @router.post("/{name}")
    async def save_profile(name: str, _: str = Depends(verify_token)):
        """
        POST /profiles/{name} — 현재 크레덴셜을 프로필로 저장
        """
        try:
            swapper.save_current_as(name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return {"name": name, "saved": True}

    @router.post("/{name}/activate")
    async def activate_profile(name: str, _: str = Depends(verify_token)):
        """
        POST /profiles/{name}/activate — 프로필 활성화 (크레덴셜 교체)
        """
        try:
            swapper.activate(name)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except OSError as e:
            logger.error(f"크레덴셜 교체 실패: {e}")
            raise HTTPException(
                status_code=500, detail="크레덴셜 파일 교체 중 오류 발생"
            )

        return {"activated": name}

    @router.delete("/{name}")
    async def delete_profile(name: str, _: str = Depends(verify_token)):
        """
        DELETE /profiles/{name} — 프로필 삭제
        """
        try:
            deleted = store.delete(name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"프로필이 존재하지 않습니다: {name}",
            )
        return {"deleted": True, "name": name}

    # === Rate Limit 엔드포인트 ===

    @router.get("/rate-limits")
    async def get_all_rate_limits(_: str = Depends(verify_token)):
        """
        GET /profiles/rate-limits — 전체 프로필의 rate limit 현황
        """
        if rate_limit_tracker is None:
            raise HTTPException(
                status_code=501,
                detail="Rate limit tracker가 초기화되지 않았습니다",
            )
        active = store.get_active()
        all_states = rate_limit_tracker.get_all_states()

        profiles_data = []
        for name, state in all_states.items():
            profiles_data.append({
                "name": name,
                "five_hour": state["five_hour"],
                "seven_day": state["seven_day"],
            })

        return {
            "active_profile": active,
            "profiles": profiles_data,
        }

    @router.get("/{name}/rate-limits")
    async def get_profile_rate_limits(
        name: str, _: str = Depends(verify_token)
    ):
        """
        GET /profiles/{name}/rate-limits — 특정 프로필의 rate limit 현황
        """
        if rate_limit_tracker is None:
            raise HTTPException(
                status_code=501,
                detail="Rate limit tracker가 초기화되지 않았습니다",
            )
        state = rate_limit_tracker.get_profile_state(name)
        return {
            "name": name,
            "five_hour": state["five_hour"],
            "seven_day": state["seven_day"],
        }

    return router
