"""웹 캐시 매니저 테스트"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from seosoyoung.web.cache import WebCache


class TestWebCacheGetFilePath:
    """캐시 파일 경로 생성 테스트"""

    def test_generates_md5_hash_filename(self):
        """URL을 MD5 해시로 변환하여 파일명 생성"""
        cache = WebCache(cache_dir="/tmp/test_cache")
        url = "https://example.com/article"

        path = cache.get_cache_file_path(url)

        # MD5 해시 + .json 확장자
        assert path.endswith(".json")
        # 경로에 cache_dir 포함
        assert "/tmp/test_cache" in path or "\\tmp\\test_cache" in path

    def test_same_url_same_path(self):
        """동일 URL은 동일 경로 반환"""
        cache = WebCache(cache_dir="/tmp/test_cache")
        url = "https://example.com/article"

        path1 = cache.get_cache_file_path(url)
        path2 = cache.get_cache_file_path(url)

        assert path1 == path2

    def test_different_url_different_path(self):
        """다른 URL은 다른 경로 반환"""
        cache = WebCache(cache_dir="/tmp/test_cache")

        path1 = cache.get_cache_file_path("https://example.com/article1")
        path2 = cache.get_cache_file_path("https://example.com/article2")

        assert path1 != path2


class TestWebCacheSaveLoad:
    """캐시 저장/로드 테스트"""

    def test_save_and_load(self, tmp_path):
        """데이터 저장 후 로드"""
        cache = WebCache(cache_dir=str(tmp_path))
        url = "https://example.com/article"
        data = {
            "title": "Test Article",
            "text": "This is test content",
            "published_date": "2024-01-15",
            "authors": ["John Doe"],
        }

        cache.save(url, data)
        loaded = cache.load(url)

        assert loaded == data

    def test_load_nonexistent_returns_none(self, tmp_path):
        """존재하지 않는 캐시 로드 시 None 반환"""
        cache = WebCache(cache_dir=str(tmp_path))

        result = cache.load("https://nonexistent.com/page")

        assert result is None

    def test_save_creates_directory(self, tmp_path):
        """저장 시 디렉토리 자동 생성"""
        cache_dir = tmp_path / "nested" / "cache" / "dir"
        cache = WebCache(cache_dir=str(cache_dir))
        url = "https://example.com/article"
        data = {"title": "Test"}

        cache.save(url, data)

        assert cache_dir.exists()
        assert cache.load(url) == data


class TestWebCacheExists:
    """캐시 존재 여부 확인 테스트"""

    def test_exists_returns_true_when_cached(self, tmp_path):
        """캐시 존재 시 True 반환"""
        cache = WebCache(cache_dir=str(tmp_path))
        url = "https://example.com/article"
        cache.save(url, {"title": "Test"})

        assert cache.exists(url) is True

    def test_exists_returns_false_when_not_cached(self, tmp_path):
        """캐시 미존재 시 False 반환"""
        cache = WebCache(cache_dir=str(tmp_path))

        assert cache.exists("https://example.com/uncached") is False


class TestWebCacheDelete:
    """캐시 삭제 테스트"""

    def test_delete_removes_cache(self, tmp_path):
        """캐시 삭제"""
        cache = WebCache(cache_dir=str(tmp_path))
        url = "https://example.com/article"
        cache.save(url, {"title": "Test"})

        cache.delete(url)

        assert cache.exists(url) is False

    def test_delete_nonexistent_no_error(self, tmp_path):
        """존재하지 않는 캐시 삭제 시 에러 없음"""
        cache = WebCache(cache_dir=str(tmp_path))

        # 에러 없이 실행되어야 함
        cache.delete("https://example.com/nonexistent")


class TestWebCacheEncoding:
    """인코딩 테스트"""

    def test_handles_korean_content(self, tmp_path):
        """한글 콘텐츠 처리"""
        cache = WebCache(cache_dir=str(tmp_path))
        url = "https://example.com/korean"
        data = {
            "title": "한글 제목",
            "text": "한글 본문 내용입니다.",
            "authors": ["김철수"],
        }

        cache.save(url, data)
        loaded = cache.load(url)

        assert loaded["title"] == "한글 제목"
        assert loaded["text"] == "한글 본문 내용입니다."

    def test_handles_special_characters(self, tmp_path):
        """특수문자 처리"""
        cache = WebCache(cache_dir=str(tmp_path))
        url = "https://example.com/special"
        data = {
            "title": "Test & <Special> \"Characters\"",
            "text": "Content with emoji: \U0001f600 and newlines:\n\nParagraph",
        }

        cache.save(url, data)
        loaded = cache.load(url)

        assert loaded == data
