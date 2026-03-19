"""슬랙 파일 다운로드 및 처리 유틸리티

슬랙에 첨부된 파일을 다운로드하여 Claude Code에 전달할 수 있도록 처리합니다.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)

# 임시 파일 저장 경로 (.local/tmp/slack_files)
TMP_DIR = Path.cwd() / ".local" / "tmp" / "slack_files"

# 지원 파일 타입 분류
TEXT_EXTENSIONS = {
    ".txt", ".md", ".yaml", ".yml", ".json", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".html", ".css", ".scss", ".xml", ".csv", ".toml", ".ini",
    ".sh", ".bash", ".ps1", ".bat", ".cmd", ".sql", ".r", ".rb", ".go",
    ".rs", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".vue", ".svelte", ".astro", ".log", ".conf", ".cfg", ".env",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

BINARY_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".zip"}


class SlackFile(TypedDict):
    """슬랙 파일 정보"""
    id: str
    name: str
    mimetype: str
    filetype: str
    size: int
    url_private: str


class DownloadedFile(TypedDict):
    """다운로드된 파일 정보"""
    local_path: str
    original_name: str
    size: int
    file_type: str  # "text", "image", "binary"
    content: str | None  # 텍스트 파일인 경우 내용


def get_file_type(filename: str) -> str:
    """파일 확장자로 타입 분류"""
    ext = Path(filename).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in BINARY_EXTENSIONS:
        return "binary"
    # 알 수 없는 확장자는 텍스트로 시도
    return "unknown"


def ensure_tmp_dir(thread_ts: str) -> Path:
    """스레드별 임시 폴더 생성"""
    # thread_ts에서 점 제거 (파일시스템 호환)
    safe_ts = thread_ts.replace(".", "_")
    dir_path = TMP_DIR / safe_ts
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def cleanup_thread_files(thread_ts: str) -> None:
    """스레드의 임시 파일 정리"""
    safe_ts = thread_ts.replace(".", "_")
    dir_path = TMP_DIR / safe_ts
    if dir_path.exists():
        try:
            shutil.rmtree(dir_path)
            logger.info(f"임시 파일 정리 완료: {dir_path}")
        except Exception as e:
            logger.warning(f"임시 파일 정리 실패: {dir_path} - {e}")


def cleanup_all_files() -> None:
    """모든 임시 파일 정리"""
    if TMP_DIR.exists():
        try:
            shutil.rmtree(TMP_DIR)
            logger.info(f"전체 임시 파일 정리 완료: {TMP_DIR}")
        except Exception as e:
            logger.warning(f"전체 임시 파일 정리 실패: {TMP_DIR} - {e}")


async def download_file(
    file_info: SlackFile,
    thread_ts: str,
) -> DownloadedFile | None:
    """슬랙 파일 다운로드

    Args:
        file_info: 슬랙 파일 정보 (event["files"]의 각 항목)
        thread_ts: 스레드 타임스탬프

    Returns:
        DownloadedFile 또는 None (실패 시)
    """
    file_id = file_info.get("id", "unknown")
    file_name = file_info.get("name", "unknown")
    file_size = file_info.get("size", 0)
    url = file_info.get("url_private", "")

    if not url:
        logger.warning(f"파일 URL 없음: {file_name}")
        return None

    try:
        # 임시 폴더 확보
        tmp_dir = ensure_tmp_dir(thread_ts)

        # 파일명에 슬랙 file_id를 포함하여 중복 방지
        # 예: image.png -> image_F0AAVCNQ4K0.png
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        local_path = tmp_dir / f"{stem}_{file_id}{suffix}"

        # 파일 다운로드 (Bot Token 인증)
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {os.environ.get('SLACK_BOT_TOKEN', '')}"}
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            # 파일 저장
            with open(local_path, "wb") as f:
                f.write(response.content)

        file_type = get_file_type(file_name)
        content = None

        # 텍스트 파일이면 내용 읽기
        if file_type == "text":
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # UTF-8 실패 시 다른 인코딩 시도
                try:
                    with open(local_path, "r", encoding="cp949") as f:
                        content = f.read()
                except Exception:
                    logger.warning(f"텍스트 파일 읽기 실패: {file_name}")
                    file_type = "binary"
        elif file_type == "unknown":
            # 알 수 없는 타입은 텍스트로 시도
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_type = "text"
            except Exception:
                file_type = "binary"

        logger.info(f"파일 다운로드 완료: {file_name} -> {local_path} (type={file_type})")

        return {
            "local_path": str(local_path.resolve()),
            "original_name": file_name,
            "size": file_size,
            "file_type": file_type,
            "content": content,
        }

    except httpx.HTTPError as e:
        logger.error(f"파일 다운로드 HTTP 오류: {file_name} - {e}")
        return None
    except Exception as e:
        logger.error(f"파일 다운로드 실패: {file_name} - {e}")
        return None


async def download_files_from_event(
    event: dict,
    thread_ts: str,
) -> list[DownloadedFile]:
    """이벤트에서 파일들을 다운로드 (async 버전)

    Args:
        event: 슬랙 이벤트 (app_mention 또는 message)
        thread_ts: 스레드 타임스탬프

    Returns:
        다운로드된 파일 목록
    """
    files = event.get("files", [])
    if not files:
        return []

    downloaded = []
    for file_info in files:
        result = await download_file(file_info, thread_ts)
        if result:
            downloaded.append(result)

    return downloaded


def download_files_sync(
    event: dict,
    thread_ts: str,
) -> list[DownloadedFile]:
    """이벤트에서 파일들을 다운로드 (동기 버전)

    ThreadPoolExecutor 환경(Slack Bolt 핸들러)에서 안전하게 사용할 수 있습니다.
    새 이벤트 루프를 생성하여 async 함수를 실행합니다.

    Args:
        event: 슬랙 이벤트 (app_mention 또는 message)
        thread_ts: 스레드 타임스탬프

    Returns:
        다운로드된 파일 목록
    """
    import asyncio

    files = event.get("files", [])
    if not files:
        return []

    # 새 이벤트 루프 생성하여 실행
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(download_files_from_event(event, thread_ts))
    finally:
        loop.close()


def build_file_context(files: list[DownloadedFile]) -> str:
    """파일 정보를 프롬프트 컨텍스트로 구성

    Args:
        files: 다운로드된 파일 목록

    Returns:
        프롬프트에 추가할 파일 컨텍스트 문자열
    """
    if not files:
        return ""

    context_parts = []
    context_parts.append("\n첨부된 파일:")

    for file in files:
        name = file["original_name"]
        path = file["local_path"]
        file_type = file["file_type"]
        content = file["content"]

        if file_type == "text" and content is not None:
            # 텍스트 파일: 내용을 프롬프트에 포함
            # 너무 길면 잘라내기 (100KB 제한)
            if len(content) > 100_000:
                content = content[:100_000] + "\n... (이하 생략)"
            context_parts.append(f"\n📄 {name}:")
            context_parts.append(f"```\n{content}\n```")
        elif file_type == "image":
            # 이미지: 경로 안내 (Read 도구로 확인 가능)
            context_parts.append(f"\n🖼️ {name}:")
            context_parts.append(f"  경로: {path}")
            context_parts.append("  (Read 도구로 이미지를 확인할 수 있습니다)")
        else:
            # 바이너리/기타: 경로 안내
            context_parts.append(f"\n📎 {name}:")
            context_parts.append(f"  경로: {path}")
            context_parts.append(f"  크기: {file['size']:,} bytes")

    return "\n".join(context_parts)
