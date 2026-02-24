"""웹 캐시 관련 설정 테스트"""

import os
from pathlib import Path

import pytest


class TestWebCacheConfig:
    """웹 캐시 경로 설정 테스트"""

    def test_get_web_cache_path_default(self, monkeypatch):
        """환경변수 없을 때 기본 경로 반환"""
        monkeypatch.delenv("WEB_CACHE_PATH", raising=False)

        # 모듈 다시 로드하여 환경변수 변경 반영
        from seosoyoung.slackbot.config import Config

        result = Config.get_web_cache_path()
        expected = str(Path.cwd() / ".local/cache/web")
        assert result == expected

    def test_get_web_cache_path_from_env(self, monkeypatch):
        """환경변수 설정 시 해당 경로 반환"""
        custom_path = "/custom/cache/path"
        monkeypatch.setenv("WEB_CACHE_PATH", custom_path)

        from seosoyoung.slackbot.config import Config

        result = Config.get_web_cache_path()
        assert result == custom_path

    def test_web_cache_path_is_string(self, monkeypatch):
        """반환값이 문자열 타입인지 확인"""
        monkeypatch.delenv("WEB_CACHE_PATH", raising=False)

        from seosoyoung.slackbot.config import Config

        result = Config.get_web_cache_path()
        assert isinstance(result, str)
