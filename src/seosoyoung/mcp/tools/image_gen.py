"""이미지 생성 및 슬랙 업로드 MCP 도구"""

import logging
import os
from pathlib import Path

from slack_sdk import WebClient

from seosoyoung.image_gen import generate_image
from seosoyoung.mcp.config import SLACK_BOT_TOKEN

logger = logging.getLogger(__name__)


async def generate_and_upload_image(
    prompt: str,
    channel: str,
    thread_ts: str,
    reference_image_paths: str = "",
) -> dict:
    """이미지를 생성하고 슬랙 스레드에 업로드

    Args:
        prompt: 이미지 생성 프롬프트
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
        reference_image_paths: 레퍼런스 이미지 절대 경로 (쉼표 구분, 선택)

    Returns:
        dict: success, message, file_name(성공 시) 키를 포함하는 결과
    """

    # 레퍼런스 이미지 경로 파싱
    ref_images = None
    if reference_image_paths:
        ref_images = [p.strip() for p in reference_image_paths.split(",") if p.strip()]

    try:
        generated = await generate_image(prompt, reference_images=ref_images)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except RuntimeError as e:
        return {"success": False, "message": str(e)}

    # 슬랙 업로드
    try:
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.files_upload_v2(
            channel=channel,
            thread_ts=thread_ts,
            file=str(generated.path),
            filename=generated.path.name,
            initial_comment=f"🎨 `{prompt[:80]}`",
        )
        file_name = generated.path.name
        logger.info(f"이미지 생성 및 업로드 성공: {file_name}")
    except Exception as e:
        logger.error(f"이미지 업로드 실패: {e}")
        return {"success": False, "message": f"이미지 생성은 성공했으나 업로드 실패: {e}"}
    finally:
        # 임시 파일 삭제
        try:
            os.unlink(generated.path)
        except OSError:
            pass

    return {"success": True, "message": "이미지 생성 및 업로드 완료", "file_name": file_name}
