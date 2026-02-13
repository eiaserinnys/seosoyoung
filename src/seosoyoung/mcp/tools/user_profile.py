"""Slack 사용자 프로필 조회 및 아바타 다운로드 MCP 도구"""

import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from slack_sdk import WebClient

from seosoyoung.mcp.config import SLACK_BOT_TOKEN, WORKSPACE_ROOT

logger = logging.getLogger(__name__)

AVATAR_DIR = Path(WORKSPACE_ROOT) / ".local" / "tmp" / "avatars"

VALID_SIZES = {24, 32, 48, 72, 192, 512, 1024}


def _get_slack_client() -> WebClient:
    """Slack WebClient 인스턴스 반환"""
    return WebClient(token=SLACK_BOT_TOKEN)


def get_user_profile(user_id: str) -> dict[str, Any]:
    """Slack 사용자 프로필 정보를 조회

    Args:
        user_id: Slack User ID (예: U08HWT0C6K1)

    Returns:
        dict: success, profile 키를 포함하는 결과 딕셔너리
    """
    if not user_id or not user_id.startswith("U"):
        return {"success": False, "message": f"유효하지 않은 user_id: {user_id}"}

    try:
        client = _get_slack_client()
        response = client.users_info(user=user_id)
    except Exception as e:
        logger.error(f"사용자 프로필 조회 실패: user_id={user_id}, error={e}")
        return {"success": False, "message": f"프로필 조회 실패: {e}"}

    user = response.get("user", {})
    profile = user.get("profile", {})

    image_urls = {}
    for key, value in profile.items():
        if key.startswith("image_") and isinstance(value, str):
            image_urls[key] = value

    return {
        "success": True,
        "profile": {
            "user_id": user_id,
            "display_name": profile.get("display_name", ""),
            "real_name": profile.get("real_name", ""),
            "title": profile.get("title", ""),
            "status_text": profile.get("status_text", ""),
            "status_emoji": profile.get("status_emoji", ""),
            "email": profile.get("email", ""),
            "image_urls": image_urls,
        },
    }


async def download_user_avatar(
    user_id: str, size: Optional[int] = None
) -> dict[str, Any]:
    """Slack 사용자 프로필 이미지를 다운로드

    Args:
        user_id: Slack User ID
        size: 이미지 크기 (24, 32, 48, 72, 192, 512, 1024). 기본값 512.

    Returns:
        dict: success, file_path 키를 포함하는 결과 딕셔너리
    """
    if size is None:
        size = 512

    if size not in VALID_SIZES:
        return {
            "success": False,
            "message": f"유효하지 않은 size: {size}. 허용: {sorted(VALID_SIZES)}",
        }

    # 프로필에서 이미지 URL 조회
    profile_result = get_user_profile(user_id)
    if not profile_result["success"]:
        return profile_result

    image_key = f"image_{size}"
    image_urls = profile_result["profile"]["image_urls"]
    image_url = image_urls.get(image_key)

    if not image_url:
        return {
            "success": False,
            "message": f"size {size} 이미지 URL 없음. 사용 가능: {list(image_urls.keys())}",
        }

    # 확장자 추출
    parsed = urlparse(image_url)
    path_suffix = Path(parsed.path).suffix or ".jpg"

    # 다운로드 디렉토리 생성
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    local_path = AVATAR_DIR / f"{user_id}_{size}{path_suffix}"

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(image_url)
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
    except Exception as e:
        logger.error(f"아바타 다운로드 실패: user_id={user_id}, url={image_url}, error={e}")
        return {"success": False, "message": f"이미지 다운로드 실패: {e}"}

    logger.info(f"아바타 다운로드 완료: {local_path}")
    return {
        "success": True,
        "file_path": str(local_path.resolve()),
        "message": f"아바타 다운로드 완료: {local_path.name}",
    }
