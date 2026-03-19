"""이미지 생성 및 슬랙 업로드 MCP 도구

Gemini API를 호출하여 이미지를 생성하고, 슬랙 스레드에 업로드합니다.
레퍼런스 이미지를 함께 전달하면 multimodal input으로 처리합니다.
"""

import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from slack_sdk import WebClient

from seosoyoung.mcp.config import SLACK_BOT_TOKEN

# MCP는 bot 전체 설정이 아닌 MCP 전용 env vars만 사용
_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-preview-image-generation")

logger = logging.getLogger(__name__)

# 이미지 임시 저장 경로
IMAGE_GEN_DIR = Path(".local/tmp/image_gen")

# 레퍼런스 이미지 허용 MIME 타입
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Nano Banana 2 지원 이미지 크기 (해상도 순)
_IMAGE_SIZE_ORDER = ("512px", "1K", "2K", "4K")
VALID_IMAGE_SIZES = set(_IMAGE_SIZE_ORDER)

# Nano Banana 2 지원 종횡비
VALID_ASPECT_RATIOS = {
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
}


@dataclass
class GeneratedImage:
    """생성된 이미지 결과"""
    path: Path
    mime_type: str
    prompt: str


def _load_reference_images(paths: list[str]) -> list[types.Part]:
    """레퍼런스 이미지 경로들을 Gemini Part 객체로 변환"""
    parts = []
    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            logger.warning(f"레퍼런스 이미지 파일 없음: {path_str}")
            continue
        mime, _ = mimetypes.guess_type(str(p))
        if not mime or mime not in _ALLOWED_IMAGE_MIMES:
            logger.warning(f"지원하지 않는 이미지 형식: {path_str} ({mime})")
            continue
        data = p.read_bytes()
        parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        logger.info(f"레퍼런스 이미지 로드: {path_str} ({mime}, {len(data)} bytes)")
    return parts


async def generate_image(
    prompt: str,
    model: Optional[str] = None,
    reference_images: Optional[list[str]] = None,
    image_size: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
) -> GeneratedImage:
    """Gemini API로 이미지를 생성하고 임시 파일로 저장

    Args:
        prompt: 이미지 생성 프롬프트
        model: 사용할 모델 (None이면 Config.gemini.model 사용)
        reference_images: 레퍼런스 이미지 파일 경로 목록 (선택)
        image_size: 이미지 해상도 ("512px", "1K", "2K", "4K") (선택)
        aspect_ratio: 종횡비 ("1:1", "16:9", "9:16" 등) (선택)

    Returns:
        GeneratedImage: 생성된 이미지 정보

    Raises:
        ValueError: API 키가 설정되지 않은 경우, 또는 잘못된 파라미터
        RuntimeError: 이미지 생성에 실패한 경우
    """
    if not _GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

    if image_size and image_size not in VALID_IMAGE_SIZES:
        raise ValueError(
            f"지원하지 않는 이미지 크기: {image_size}. "
            f"허용 값: {', '.join(_IMAGE_SIZE_ORDER)}"
        )

    if aspect_ratio and aspect_ratio not in VALID_ASPECT_RATIOS:
        raise ValueError(
            f"지원하지 않는 종횡비: {aspect_ratio}. "
            f"허용 값: {', '.join(sorted(VALID_ASPECT_RATIOS))}"
        )

    target_model = model or _GEMINI_MODEL
    logger.info(
        f"이미지 생성 요청: model={target_model}, prompt={prompt[:100]}"
        f"{f', size={image_size}' if image_size else ''}"
        f"{f', ratio={aspect_ratio}' if aspect_ratio else ''}"
    )

    client = genai.Client(api_key=_GEMINI_API_KEY)

    # 레퍼런스 이미지가 있으면 multimodal contents 구성
    contents = prompt
    if reference_images:
        ref_parts = _load_reference_images(reference_images)
        if ref_parts:
            logger.info(f"레퍼런스 이미지 {len(ref_parts)}개 포함하여 요청")
            contents = [*ref_parts, prompt]

    # ImageConfig 구성 (image_size, aspect_ratio가 있을 때만)
    image_config = None
    if image_size or aspect_ratio:
        config_kwargs = {}
        if image_size:
            config_kwargs["image_size"] = image_size
        if aspect_ratio:
            config_kwargs["aspect_ratio"] = aspect_ratio
        image_config = types.ImageConfig(**config_kwargs)

    response = client.models.generate_content(
        model=target_model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=image_config,
        ),
    )

    # 응답에서 이미지 데이터 추출
    if not response.candidates or not response.candidates[0].content.parts:
        raise RuntimeError("Gemini API가 빈 응답을 반환했습니다.")

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            IMAGE_GEN_DIR.mkdir(parents=True, exist_ok=True)

            mime_type = part.inline_data.mime_type
            ext = "png" if "png" in mime_type else "jpg"
            filename = f"generated_{int(time.time() * 1000)}.{ext}"
            file_path = IMAGE_GEN_DIR / filename

            file_path.write_bytes(part.inline_data.data)
            logger.info(f"이미지 저장 완료: {file_path} ({mime_type})")

            return GeneratedImage(
                path=file_path,
                mime_type=mime_type,
                prompt=prompt,
            )

    # 이미지가 없는 경우 - 텍스트 응답 확인
    text_parts = [p.text for p in response.candidates[0].content.parts if p.text]
    if text_parts:
        raise RuntimeError(
            f"이미지를 생성하지 못했습니다. Gemini 응답: {' '.join(text_parts)[:200]}"
        )

    raise RuntimeError("Gemini API 응답에서 이미지 데이터를 찾을 수 없습니다.")


async def generate_and_upload_image(
    prompt: str,
    channel: str,
    thread_ts: str,
    reference_image_paths: str = "",
    image_size: str = "",
    aspect_ratio: str = "",
) -> dict:
    """이미지를 생성하고 슬랙 스레드에 업로드

    Args:
        prompt: 이미지 생성 프롬프트
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
        reference_image_paths: 레퍼런스 이미지 절대 경로 (쉼표 구분, 선택)
        image_size: 이미지 해상도 ("512px", "1K", "2K", "4K") (선택)
        aspect_ratio: 종횡비 ("1:1", "16:9", "9:16" 등) (선택)

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
            image_size=image_size.strip() or None,
            aspect_ratio=aspect_ratio.strip() or None,
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
