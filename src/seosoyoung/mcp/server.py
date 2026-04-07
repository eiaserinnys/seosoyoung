"""seosoyoung MCP 서버 정의"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from cogito import Reflector

from seosoyoung.mcp.tools.attach import attach_file
from seosoyoung.mcp.tools.image_gen import generate_and_upload_image
from seosoyoung.mcp.tools.slack_messaging import post_message
from seosoyoung.mcp.tools.thread_files import download_thread_files
from seosoyoung.mcp.tools.user_profile import download_user_avatar, get_user_profile

logger = logging.getLogger(__name__)

mcp = FastMCP("seosoyoung-attach")

reflect = Reflector(
    name="mcp-seosoyoung",
    description=f"{os.environ.get('BOT_NAME', '봇')} 봇 전용 MCP 서버",
    version_from="git",
    source_root=str(Path(__file__).resolve().parent),
    port=3104,
    transport="sse",
)


# --- MCP Tools with cogito annotations ---


@mcp.tool()
@reflect.capability(
    name="file_attachment",
    description="슬랙 채널에 파일 첨부",
    tools=["slack_attach_file"],
)
@reflect.config("SLACK_BOT_TOKEN", sensitive=True)
def slack_attach_file(file_path: str, channel: str, thread_ts: str) -> dict:
    """슬랙에 파일을 첨부합니다.

    workspace(slackbot_workspace) 내부 파일만 허용됩니다.
    허용 확장자: .md, .txt, .yaml, .yml, .json, .csv, .png, .jpg, .pdf 등
    최대 파일 크기: 20MB

    Args:
        file_path: 첨부할 파일의 절대 경로
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
    """
    return attach_file(file_path, channel, thread_ts)


@mcp.tool()
@reflect.capability(
    name="messaging",
    description="봇 권한으로 슬랙 채널에 메시지 전송",
    tools=["slack_post_message"],
)
@reflect.config("SLACK_BOT_TOKEN", sensitive=True)
def slack_post_message(
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
    file_paths: Optional[str] = None,
) -> dict:
    """봇 권한으로 슬랙 채널에 메시지를 보냅니다.

    텍스트 전송과 파일 첨부를 모두 지원합니다.
    파일 첨부 시 workspace 내부 파일만 허용됩니다.

    Args:
        channel: 슬랙 채널 ID (필수)
        text: 메시지 텍스트 (필수)
        thread_ts: 스레드 타임스탬프 (선택)
        file_paths: 파일 경로, 쉼표 구분 (선택)
    """
    return post_message(channel, text, thread_ts or "", file_paths or "")


@mcp.tool()
@reflect.capability(
    name="image_generation",
    description="텍스트 프롬프트로 이미지를 생성하여 슬랙에 업로드",
    tools=["slack_generate_image"],
)
@reflect.config("GEMINI_API_KEY", sensitive=True)
async def slack_generate_image(
    prompt: str,
    channel: str,
    thread_ts: str,
    reference_image_paths: Optional[str] = None,
    image_size: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
) -> dict:
    """텍스트 프롬프트로 이미지를 생성하고 슬랙 스레드에 업로드합니다.

    Gemini API (Nano Banana 2)를 사용하여 이미지를 생성합니다.
    레퍼런스 이미지를 전달하면 해당 이미지를 참고하여 생성합니다.

    Args:
        prompt: 이미지 생성 프롬프트 (영어 권장)
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
        reference_image_paths: 레퍼런스 이미지 절대 경로, 쉼표 구분 (선택)
        image_size: 이미지 해상도 - "512px", "1K"(API 기본값), "2K", "4K" (선택)
        aspect_ratio: 종횡비 - "1:1"(API 기본값), "16:9", "9:16", "3:2", "2:3", "4:3", "3:4", "4:5", "5:4", "21:9", "1:4", "4:1", "1:8", "8:1" (선택)
    """
    return await generate_and_upload_image(
        prompt,
        channel,
        thread_ts,
        reference_image_paths or "",
        image_size=image_size or "",
        aspect_ratio=aspect_ratio or "",
    )


@mcp.tool()
@reflect.capability(
    name="thread_files",
    description="슬랙 스레드 내 첨부 파일 다운로드",
    tools=["slack_download_thread_files"],
)
@reflect.config("SLACK_BOT_TOKEN", sensitive=True)
async def slack_download_thread_files(channel: str, thread_ts: str) -> dict:
    """스레드 내 모든 메시지의 첨부 파일을 다운로드합니다.

    Slack conversations.replies API로 스레드 메시지를 조회하고,
    파일이 있는 메시지에서 파일을 로컬로 다운로드합니다.

    Args:
        channel: 슬랙 채널 ID
        thread_ts: 스레드 타임스탬프
    """
    return await download_thread_files(channel, thread_ts)


@mcp.tool()
@reflect.capability(
    name="user_profile",
    description="Slack 사용자 프로필 조회 및 아바타 다운로드",
    tools=["slack_get_user_profile", "slack_download_user_avatar"],
)
@reflect.config("SLACK_BOT_TOKEN", sensitive=True)
def slack_get_user_profile(user_id: str) -> dict:
    """Slack 사용자의 프로필 정보를 조회합니다.

    display_name, real_name, title, status, email, 프로필 이미지 URL 등을 반환합니다.

    Args:
        user_id: Slack User ID (예: U08HWT0C6K1)
    """
    return get_user_profile(user_id)


# NOTE: user_profile capability에 논리적으로 속하지만, cogito는
# 1 capability = 1 function 바인딩이므로 별도 데코레이터를 달지 않는다.
# tools 목록(위 @reflect.capability의 tools 파라미터)에만 선언하여 기능 범위를 나타낸다.
@mcp.tool()
async def slack_download_user_avatar(
    user_id: str, size: Optional[int] = None
) -> dict:
    """Slack 사용자의 프로필 이미지를 다운로드합니다.

    지정한 크기의 프로필 이미지를 로컬에 저장하고 절대 경로를 반환합니다.

    Args:
        user_id: Slack User ID (예: U08HWT0C6K1)
        size: 이미지 크기 (24, 32, 48, 72, 192, 512, 1024). 기본값 512.
    """
    return await download_user_avatar(user_id, size)


# --- Cogito reflection endpoints via FastMCP custom_route ---
#
# mount_cogito()는 FastAPI 전용이므로, FastMCP의 Starlette 앱에는
# custom_route()를 통해 동일한 7개 엔드포인트를 직접 등록한다.


@mcp.custom_route("/reflect", methods=["GET"])
async def reflect_level0(request: Request) -> JSONResponse:
    """Level 0: identity + capabilities."""
    return JSONResponse(reflect.get_level0())


@mcp.custom_route("/reflect/config", methods=["GET"])
async def reflect_config_all(request: Request) -> JSONResponse:
    """Level 1: all configuration entries."""
    return JSONResponse(reflect.get_level1())


@mcp.custom_route("/reflect/config/{capability_name}", methods=["GET"])
async def reflect_config_by_cap(request: Request) -> JSONResponse:
    """Level 1: configuration entries for a specific capability."""
    return JSONResponse(
        reflect.get_level1(request.path_params["capability_name"])
    )


@mcp.custom_route("/reflect/source", methods=["GET"])
async def reflect_source_all(request: Request) -> JSONResponse:
    """Level 2: all source locations."""
    return JSONResponse(reflect.get_level2())


@mcp.custom_route("/reflect/source/{capability_name}", methods=["GET"])
async def reflect_source_by_cap(request: Request) -> JSONResponse:
    """Level 2: source locations for a specific capability."""
    return JSONResponse(
        reflect.get_level2(request.path_params["capability_name"])
    )


@mcp.custom_route("/reflect/runtime", methods=["GET"])
async def reflect_runtime(request: Request) -> JSONResponse:
    """Level 3: runtime status."""
    return JSONResponse(reflect.get_level3())


@mcp.custom_route("/reflect/full", methods=["GET"])
async def reflect_full(request: Request) -> JSONResponse:
    """Full response: all levels combined."""
    return JSONResponse(reflect.get_full())
