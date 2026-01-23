"""file_handler 모듈 테스트"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from seosoyoung.slack.file_handler import (
    get_file_type,
    ensure_tmp_dir,
    cleanup_thread_files,
    download_file,
    download_files_from_event,
    build_file_context,
    TMP_DIR,
    MAX_FILE_SIZE,
)


class TestGetFileType:
    """파일 타입 분류 테스트"""

    def test_text_files(self):
        """텍스트 파일 타입 감지"""
        assert get_file_type("test.txt") == "text"
        assert get_file_type("test.md") == "text"
        assert get_file_type("test.py") == "text"
        assert get_file_type("test.yaml") == "text"
        assert get_file_type("test.json") == "text"
        assert get_file_type("test.js") == "text"
        assert get_file_type("test.ts") == "text"

    def test_image_files(self):
        """이미지 파일 타입 감지"""
        assert get_file_type("test.png") == "image"
        assert get_file_type("test.jpg") == "image"
        assert get_file_type("test.jpeg") == "image"
        assert get_file_type("test.gif") == "image"
        assert get_file_type("test.webp") == "image"

    def test_binary_files(self):
        """바이너리 파일 타입 감지"""
        assert get_file_type("test.pdf") == "binary"
        assert get_file_type("test.xlsx") == "binary"
        assert get_file_type("test.docx") == "binary"
        assert get_file_type("test.zip") == "binary"

    def test_unknown_files(self):
        """알 수 없는 파일 타입"""
        assert get_file_type("test.xyz") == "unknown"
        assert get_file_type("test") == "unknown"


class TestEnsureTmpDir:
    """임시 폴더 생성 테스트"""

    def test_creates_directory(self, tmp_path, monkeypatch):
        """스레드별 임시 폴더 생성"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        thread_ts = "1234567890.123456"
        result = ensure_tmp_dir(thread_ts)

        assert result.exists()
        assert result.name == "1234567890_123456"  # 점이 언더스코어로 변환

    def test_handles_existing_directory(self, tmp_path, monkeypatch):
        """기존 폴더가 있어도 정상 동작"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        thread_ts = "1234567890.123456"
        ensure_tmp_dir(thread_ts)  # 첫 번째 생성
        result = ensure_tmp_dir(thread_ts)  # 두 번째 호출

        assert result.exists()


class TestCleanupThreadFiles:
    """임시 파일 정리 테스트"""

    def test_removes_directory(self, tmp_path, monkeypatch):
        """스레드 폴더 삭제"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        thread_ts = "1234567890.123456"
        dir_path = ensure_tmp_dir(thread_ts)

        # 테스트 파일 생성
        (dir_path / "test.txt").write_text("test")

        cleanup_thread_files(thread_ts)

        assert not dir_path.exists()

    def test_handles_nonexistent_directory(self, tmp_path, monkeypatch):
        """존재하지 않는 폴더도 에러 없이 처리"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        # 에러 없이 실행되어야 함
        cleanup_thread_files("nonexistent.thread")


class TestDownloadFile:
    """파일 다운로드 테스트"""

    @pytest.mark.asyncio
    async def test_download_text_file(self, tmp_path, monkeypatch):
        """텍스트 파일 다운로드"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        file_content = "Hello, World!"

        # httpx 모킹
        mock_response = MagicMock()
        mock_response.content = file_content.encode("utf-8")
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_client):
            result = await download_file(
                {
                    "id": "F123",
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "filetype": "txt",
                    "size": len(file_content),
                    "url_private": "https://files.slack.com/test.txt",
                },
                "1234567890.123456",
            )

        assert result is not None
        assert result["original_name"] == "test.txt"
        assert result["file_type"] == "text"
        assert result["content"] == file_content

    @pytest.mark.asyncio
    async def test_skip_large_file(self, tmp_path, monkeypatch):
        """크기 초과 파일 스킵"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        result = await download_file(
            {
                "id": "F123",
                "name": "large.bin",
                "mimetype": "application/octet-stream",
                "filetype": "bin",
                "size": MAX_FILE_SIZE + 1,
                "url_private": "https://files.slack.com/large.bin",
            },
            "1234567890.123456",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_skip_missing_url(self, tmp_path, monkeypatch):
        """URL 없는 파일 스킵"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        result = await download_file(
            {
                "id": "F123",
                "name": "test.txt",
                "mimetype": "text/plain",
                "filetype": "txt",
                "size": 100,
                "url_private": "",  # 빈 URL
            },
            "1234567890.123456",
        )

        assert result is None


class TestDownloadFilesFromEvent:
    """이벤트에서 파일 다운로드 테스트"""

    @pytest.mark.asyncio
    async def test_no_files_in_event(self):
        """파일이 없는 이벤트"""
        event = {"text": "Hello", "user": "U123"}
        result = await download_files_from_event(event, "1234567890.123456")
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_files_list(self):
        """빈 파일 목록"""
        event = {"text": "Hello", "user": "U123", "files": []}
        result = await download_files_from_event(event, "1234567890.123456")
        assert result == []


class TestDownloadFilesSync:
    """동기 환경에서 파일 다운로드 테스트 (ThreadPoolExecutor 시뮬레이션)"""

    def test_download_in_thread_pool(self, tmp_path, monkeypatch):
        """ThreadPoolExecutor에서 파일 다운로드 - 이벤트 루프 없는 환경"""
        from concurrent.futures import ThreadPoolExecutor
        from seosoyoung.slack.file_handler import download_files_sync

        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        file_content = "Hello from thread!"

        # httpx 모킹
        mock_response = MagicMock()
        mock_response.content = file_content.encode("utf-8")
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        event = {
            "files": [
                {
                    "id": "F123",
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "filetype": "txt",
                    "size": len(file_content),
                    "url_private": "https://files.slack.com/test.txt",
                }
            ]
        }

        with patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_client):
            # ThreadPoolExecutor에서 실행 (Slack Bolt 환경 시뮬레이션)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(download_files_sync, event, "1234567890.123456")
                result = future.result(timeout=10)

        assert len(result) == 1
        assert result[0]["original_name"] == "test.txt"
        assert result[0]["content"] == file_content

    def test_download_image_in_thread_pool(self, tmp_path, monkeypatch):
        """ThreadPoolExecutor에서 이미지 파일 다운로드"""
        from concurrent.futures import ThreadPoolExecutor
        from seosoyoung.slack.file_handler import download_files_sync

        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        # 가짜 PNG 데이터
        image_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_response = MagicMock()
        mock_response.content = image_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        event = {
            "files": [
                {
                    "id": "F456",
                    "name": "screenshot.png",
                    "mimetype": "image/png",
                    "filetype": "png",
                    "size": len(image_content),
                    "url_private": "https://files.slack.com/screenshot.png",
                }
            ]
        }

        with patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_client):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(download_files_sync, event, "1234567890.123456")
                result = future.result(timeout=10)

        assert len(result) == 1
        assert result[0]["original_name"] == "screenshot.png"
        assert result[0]["file_type"] == "image"
        assert Path(result[0]["local_path"]).exists()


class TestBuildFileContext:
    """파일 컨텍스트 생성 테스트"""

    def test_empty_files(self):
        """빈 파일 목록"""
        result = build_file_context([])
        assert result == ""

    def test_text_file_context(self):
        """텍스트 파일 컨텍스트"""
        files = [
            {
                "local_path": "/tmp/test.txt",
                "original_name": "test.txt",
                "size": 100,
                "file_type": "text",
                "content": "Hello, World!",
            }
        ]
        result = build_file_context(files)

        assert "첨부된 파일:" in result
        assert "test.txt" in result
        assert "Hello, World!" in result

    def test_image_file_context(self):
        """이미지 파일 컨텍스트"""
        files = [
            {
                "local_path": "/tmp/image.png",
                "original_name": "image.png",
                "size": 1024,
                "file_type": "image",
                "content": None,
            }
        ]
        result = build_file_context(files)

        assert "첨부된 파일:" in result
        assert "image.png" in result
        assert "/tmp/image.png" in result
        assert "Read 도구로 이미지를 확인" in result

    def test_binary_file_context(self):
        """바이너리 파일 컨텍스트"""
        files = [
            {
                "local_path": "/tmp/doc.pdf",
                "original_name": "doc.pdf",
                "size": 2048,
                "file_type": "binary",
                "content": None,
            }
        ]
        result = build_file_context(files)

        assert "첨부된 파일:" in result
        assert "doc.pdf" in result
        assert "2,048 bytes" in result

    def test_multiple_files_context(self):
        """여러 파일 컨텍스트"""
        files = [
            {
                "local_path": "/tmp/test.txt",
                "original_name": "test.txt",
                "size": 100,
                "file_type": "text",
                "content": "Text content",
            },
            {
                "local_path": "/tmp/image.png",
                "original_name": "image.png",
                "size": 1024,
                "file_type": "image",
                "content": None,
            },
        ]
        result = build_file_context(files)

        assert "test.txt" in result
        assert "image.png" in result
