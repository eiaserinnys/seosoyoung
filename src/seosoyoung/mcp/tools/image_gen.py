"""이미지 생성 및 슬랙 업로드 MCP 도구

OpenAI gpt-image-2 API를 호출하여 이미지를 생성하고, 슬랙 스레드에 업로드합니다.
레퍼런스 이미지를 함께 전달하면 images.edit() 엔드포인트로 처리합니다.
"""

import base64
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from slack_sdk import WebClient

from seosoyoung.mcp.config import SLACK_BOT_TOKEN

_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_MODEL = "gpt-image-2"

logger = logging.getLogger(__name__)

# 이미지 임시 저장 경로
IMAGE_GEN_DIR = Path(".local/tmp/image_gen")

# 레퍼런스 이미지 허용 MIME 타입
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# gpt-image-2 지원 이미지 크기
VALID_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}

# gpt-image-2 지원 품질
VALID_QUALITIES = {"low", "medium", "high"}


@dataclass
class GeneratedImage:
    """생성된 이미지 결과"""
    path: Path
    mime_type: str
    prompt: str


def _validate_reference_images(paths: list[str]) -> list[Path]:
    """레퍼런스 이미지 경로들을 검증하고 유효한 Path 리스트 반환"""
    validated = []
    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            logger.warning(f"레퍼런스 이미지 파일 없음: {path_str}")
            continue
        if p.suffix.lower() not in _ALLOWED_IMAGE_EXTS:
            logger.warning(f"지원하지 않는 이미지 형식: {path_str} ({p.suffix})")
            continue
        logger.info(f"레퍼런스 이미지 확인: {path_str} ({p.stat().st_size} bytes)")
        validated.append(p)
    return validated


async def generate_image(
    prompt: str,
    reference_images: Optional[list[str]] = None,
    size: Optional[str] = None,
    quality: Optional[str] = None,
) -> GeneratedImage:
    """OpenAI gpt-image-2 API로 이미지를 생성하고 임시 파일로 저장

    Args:
        prompt: 이미지 생성 프롬프트
        reference_images: 레퍼런스 이미지 파일 경로 목록 (선택)
        size: 이미지 크기 ("1024x1024", "1024x1536", "1536x1024", "auto") (선택)
        quality: 이미지 품질 ("low", "medium", "high") (선택)

    Returns:
        GeneratedImage: 생성된 이미지 정보

    Raises:
        ValueError: API 키가 설정되지 않은 경우, 또는 잘못된 파라미터
        RuntimeError: 이미지 생성에 실패한 경우
    """
    if not _OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

    if size and size not in VALID_SIZES:
        raise ValueError(
            f"지원하지 않는 이미지 크기: {size}. "
            f"허용 값: {', '.join(sorted(VALID_SIZES))}"
        )

    if quality and quality not in VALID_QUALITIES:
        raise ValueError(
            f"지원하지 않는 품질: {quality}. "
            f"허용 값: {', '.join(sorted(VALID_QUALITIES))}"
        )

    logger.info(
        f"이미지 생성 요청: model={_MODEL}, prompt={prompt[:100]}"
        f"{f', size={size}' if size else ''}"
        f"{f', quality={quality}' if quality else ''}"
    )

    client = AsyncOpenAI(api_key=_OPENAI_API_KEY)

    # 레퍼런스 이미지가 있으면 images.edit() 사용
    if reference_images:
        validated_paths = _validate_reference_images(reference_images)
        if validated_paths:
            logger.info(f"레퍼런스 이미지 {len(validated_paths)}개 포함하여 요청")
            image_files = [open(p, "rb") for p in validated_paths]
            try:
                response = await client.images.edit(
                    model=_MODEL,
                    image=image_files,
                    prompt=prompt,
                    n=1,
                    size=size or "auto",
                    quality=quality or "auto",
                )
            finally:
                for f in image_files:
                    f.close()
        else:
            # 유효한 레퍼런스가 없으면 text-to-image 폴백
            response = await client.images.generate(
                model=_MODEL,
                prompt=prompt,
                n=1,
                size=size or "auto",
                quality=quality or "auto",
            )
    else:
        # text-to-image
        response = await client.images.generate(
            model=_MODEL,
            prompt=prompt,
            n=1,
            size=size or "auto",
            quality=quality or "auto",
        )

    # 응답에서 이미지 데이터 추출
    if not response.data:
        raise RuntimeError("OpenAI API가 빈 응답을 반환했습니다.")

    b64_json = response.data[0].b64_json
    if not b64_json:
        raise RuntimeError("OpenAI API 응답에서 이미지 데이터를 찾을 수 없습니다.")

    image_bytes = base64.b64decode(b64_json)

    IMAGE_GEN_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"generated_{int(time.time() * 1000)}.png"
    file_path = IMAGE_GEN_DIR / filename
    file_path.write_bytes(image_bytes)
    logger.info(f"이미지 저장 완료: {file_path} (image/png, {len(image_bytes)} bytes)")

    return GeneratedImage(
        path=file_path,
        mime_type="image/png",
        prompt=prompt,
    )


async def generate_and_upload_image(
    prompt: str,
    channel: str,
    thread_ts: str,
    reference_image_paths: str = "",
    size: str = "",
    quality: str = "",
) -> dict:
    """이미지를 생성하고 슬랙 스레드에 업로드

    Args:
        prompt: 이미지 생성 프롬프트
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
        reference_image_paths: 레퍼런스 이미지 절대 경로 (쉼표 구분, 선택)
        size: 이미지 크기 ("1024x1024", "1024x1536", "1536x1024", "auto") (선택)
        quality: 이미지 품질 ("low", "medium", "high") (선택)

    Returns:
        dict: success, message, file_name(성공 시) 키를 포함하는 결과
    """

    # 레퍼런스 이미지 경로 파싱
    ref_images = None
    if reference_image_paths:
        ref_images = [p.strip() for p in reference_image_paths.split(",") if p.strip()]

    try:
        generated = await generate_image(
            prompt,
            reference_images=ref_images,
            size=size.strip() or None,
            quality=quality.strip() or None,
        )
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
            initial_comment=f"\U0001f3a8 `{prompt[:80]}`",
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
