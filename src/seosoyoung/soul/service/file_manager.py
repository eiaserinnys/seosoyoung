"""
FileManager - 첨부 파일 관리

첨부 파일 업로드, 검증, 정리를 담당합니다.
"""

import os
import time
import shutil
import mimetypes
from pathlib import Path
from typing import Optional

import aiofiles

from seosoyoung.soul.constants import MAX_ATTACHMENT_SIZE, DANGEROUS_EXTENSIONS


# 기본 설정
DEFAULT_ATTACHMENT_DIR = "/tmp/claude-code-attachments"


class AttachmentError(Exception):
    """첨부 파일 처리 오류"""
    pass


class FileManager:
    """
    첨부 파일 관리자

    역할:
    1. 첨부 파일 저장 (스레드별 격리)
    2. 파일 검증 (크기, 확장자)
    3. 스레드 첨부 파일 정리
    """

    def __init__(
        self,
        base_dir: Optional[str] = None,
        max_size: int = MAX_ATTACHMENT_SIZE
    ):
        """
        Args:
            base_dir: 첨부 파일 저장 기본 디렉토리
            max_size: 최대 파일 크기 (bytes)
        """
        self._base_dir = Path(
            base_dir or os.getenv("ATTACHMENT_DIR", DEFAULT_ATTACHMENT_DIR)
        )
        self._max_size = max_size
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def get_thread_dir(self, thread_id: int) -> Path:
        """스레드별 첨부 파일 디렉토리"""
        thread_dir = self._base_dir / str(thread_id)
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def validate_file(self, filename: str, size: int) -> None:
        """
        파일 검증

        Args:
            filename: 파일명
            size: 파일 크기 (bytes)

        Raises:
            AttachmentError: 검증 실패
        """
        # 크기 검증
        if size > self._max_size:
            raise AttachmentError(
                f"파일이 너무 큽니다 ({size // 1024 // 1024}MB > {self._max_size // 1024 // 1024}MB)"
            )

        # 확장자 검증
        suffix = Path(filename).suffix.lower()
        if suffix in DANGEROUS_EXTENSIONS:
            raise AttachmentError(
                f"보안상 허용되지 않는 파일 형식입니다: {suffix}"
            )

    async def save_file(
        self,
        thread_id: int,
        filename: str,
        content: bytes
    ) -> dict:
        """
        파일 저장

        Args:
            thread_id: 스레드 ID
            filename: 원본 파일명
            content: 파일 내용

        Returns:
            저장 결과 딕셔너리

        Raises:
            AttachmentError: 검증 실패
        """
        # 검증
        self.validate_file(filename, len(content))

        # 파일명 안전하게 변환 (타임스탬프 추가)
        timestamp = int(time.time() * 1000)
        safe_filename = f"{timestamp}_{filename}"
        thread_dir = self.get_thread_dir(thread_id)
        file_path = thread_dir / safe_filename

        # 저장 (비동기 I/O)
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # MIME 타입 추측
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

        return {
            "path": str(file_path),
            "filename": filename,
            "size": len(content),
            "content_type": content_type,
        }

    def is_safe_path(self, path: str, workspace_dir: Optional[str] = None) -> bool:
        """
        파일 경로 보안 검증

        Args:
            path: 검사할 경로
            workspace_dir: 허용된 워크스페이스 디렉토리

        Returns:
            True if safe, False otherwise
        """
        try:
            resolved = Path(path).resolve()
            resolved_str = str(resolved)

            # 허용된 디렉토리 확인
            allowed = False

            # 1. 첨부 파일 디렉토리
            if resolved_str.startswith(str(self._base_dir)):
                allowed = True

            # 2. 임시 Claude Code 디렉토리
            if resolved_str.startswith('/tmp/claude-code-'):
                allowed = True

            # 3. 워크스페이스 디렉토리
            if workspace_dir and resolved_str.startswith(workspace_dir):
                allowed = True

            if not allowed:
                return False

            # 위험한 확장자 체크
            if resolved.suffix.lower() in DANGEROUS_EXTENSIONS:
                return False

            # 파일 존재 확인
            if not resolved.exists():
                return False

            # 디렉토리 여부 확인
            if resolved.is_dir():
                return False

            # 크기 확인
            if resolved.stat().st_size > self._max_size:
                return False

            return True

        except Exception:
            return False

    def cleanup_thread(self, thread_id: int) -> int:
        """
        스레드의 첨부 파일 정리

        Args:
            thread_id: 스레드 ID

        Returns:
            삭제된 파일 수
        """
        thread_dir = self._base_dir / str(thread_id)
        if not thread_dir.exists():
            return 0

        try:
            # 파일 수 계산
            files_removed = sum(1 for _ in thread_dir.iterdir() if _.is_file())
            # 디렉토리 전체 삭제
            shutil.rmtree(thread_dir)
            return files_removed
        except Exception:
            return 0

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        오래된 첨부 파일 정리

        Args:
            max_age_hours: 최대 보관 시간 (시간)

        Returns:
            삭제된 디렉토리 수
        """
        max_age_seconds = max_age_hours * 3600
        current_time = time.time()
        cleaned = 0

        if not self._base_dir.exists():
            return 0

        for thread_dir in self._base_dir.iterdir():
            if not thread_dir.is_dir():
                continue

            try:
                # 디렉토리 수정 시간 확인
                mtime = thread_dir.stat().st_mtime
                if current_time - mtime > max_age_seconds:
                    shutil.rmtree(thread_dir)
                    cleaned += 1
            except Exception:
                continue

        return cleaned

    def get_stats(self) -> dict:
        """첨부 파일 통계"""
        total_files = 0
        total_size = 0
        thread_count = 0

        if self._base_dir.exists():
            for thread_dir in self._base_dir.iterdir():
                if thread_dir.is_dir():
                    thread_count += 1
                    for file_path in thread_dir.iterdir():
                        if file_path.is_file():
                            total_files += 1
                            total_size += file_path.stat().st_size

        return {
            "base_dir": str(self._base_dir),
            "thread_count": thread_count,
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_file_size_mb": self._max_size // (1024 * 1024),
        }


# 싱글톤 인스턴스
file_manager = FileManager()
