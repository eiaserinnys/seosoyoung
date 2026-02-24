"""웹 콘텐츠 캐시 관리"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class WebCache:
    """URL 기반 웹 콘텐츠 캐시 관리자"""

    def __init__(self, cache_dir: str):
        """
        Args:
            cache_dir: 캐시 파일을 저장할 디렉토리 경로
        """
        self.cache_dir = cache_dir

    def get_cache_file_path(self, url: str) -> str:
        """URL에 해당하는 캐시 파일 경로 반환

        Args:
            url: 캐시할 URL

        Returns:
            캐시 파일의 전체 경로
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def _ensure_dir(self) -> None:
        """캐시 디렉토리가 없으면 생성"""
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def save(self, url: str, data: dict[str, Any]) -> None:
        """캐시 데이터 저장

        Args:
            url: 원본 URL
            data: 저장할 데이터 딕셔너리
        """
        self._ensure_dir()
        cache_path = self.get_cache_file_path(url)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, url: str) -> dict[str, Any] | None:
        """캐시 데이터 로드

        Args:
            url: 원본 URL

        Returns:
            캐시된 데이터 또는 None (캐시 미존재 시)
        """
        cache_path = self.get_cache_file_path(url)
        if not os.path.exists(cache_path):
            return None
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def exists(self, url: str) -> bool:
        """캐시 존재 여부 확인

        Args:
            url: 확인할 URL

        Returns:
            캐시 존재 여부
        """
        return os.path.exists(self.get_cache_file_path(url))

    def delete(self, url: str) -> None:
        """캐시 삭제

        Args:
            url: 삭제할 URL의 캐시
        """
        cache_path = self.get_cache_file_path(url)
        if os.path.exists(cache_path):
            os.remove(cache_path)
