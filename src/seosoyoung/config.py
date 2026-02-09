"""설정 관리

카테고리별로 구분된 설정을 관리합니다.
- 경로 설정: get_*() 메서드 (cwd 기준 계산 필요)
- 그 외 설정: 클래스 변수 (모듈 로드 시 평가)
"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(Exception):
    """설정 오류 예외

    필수 환경변수 누락 등 설정 관련 오류 시 발생합니다.
    """

    def __init__(self, missing_vars: List[str]):
        self.missing_vars = missing_vars
        message = f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}"
        super().__init__(message)


def _get_path(env_var: str, default_subdir: str) -> str:
    """환경변수가 없으면 현재 경로 하위 폴더 반환"""
    env_value = os.getenv(env_var)
    if env_value:
        return env_value
    return str(Path.cwd() / default_subdir)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """문자열을 bool로 변환"""
    if value is None:
        return default
    return value.lower() == "true"


def _parse_int(value: str | None, default: int) -> int:
    """문자열을 int로 변환"""
    if value is None or value == "":
        return default
    return int(value)


def _parse_float(value: str | None, default: float) -> float:
    """문자열을 float로 변환"""
    if value is None or value == "":
        return default
    return float(value)


class Config:
    """애플리케이션 설정

    설정 접근 방식:
    - 경로 관련: get_*() 메서드 (런타임에 cwd 기준 계산)
    - 그 외: 클래스 변수 (모듈 로드 시 평가)
    """

    # ========================================
    # Slack 설정
    # ========================================
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
    BOT_USER_ID: str | None = None  # 런타임에 auth.test()로 설정

    # ========================================
    # Recall 설정 (도구 선택 사전 분석)
    # ========================================
    RECALL_API_KEY = os.getenv("RECALL_API_KEY")
    RECALL_ENABLED = _parse_bool(os.getenv("RECALL_ENABLED"), False)
    RECALL_MODEL = os.getenv("RECALL_MODEL", "claude-3-5-haiku-latest")
    RECALL_THRESHOLD = _parse_int(os.getenv("RECALL_THRESHOLD"), 5)
    RECALL_TIMEOUT = _parse_float(os.getenv("RECALL_TIMEOUT"), 10.0)

    # ========================================
    # 권한 설정
    # ========================================
    ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
    ADMIN_USERS = [u.strip() for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]

    ROLE_TOOLS = {
        "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
        "viewer": ["Read", "Glob", "Grep"],
    }

    # ========================================
    # 디버그 설정
    # ========================================
    DEBUG = _parse_bool(os.getenv("DEBUG"), False)
    TRELLO_POLLING_DEBUG = _parse_bool(os.getenv("TRELLO_POLLING_DEBUG"), False)

    # ========================================
    # 알림 설정
    # ========================================
    NOTIFY_CHANNEL = os.getenv("NOTIFY_CHANNEL", "")

    # ========================================
    # Trello 설정
    # ========================================
    TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
    TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
    TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")
    TRELLO_NOTIFY_CHANNEL = os.getenv("TRELLO_NOTIFY_CHANNEL", "")

    TRELLO_WATCH_LISTS = {
        "to_go": os.getenv("TRELLO_TO_GO_LIST_ID", ""),
    }

    TRELLO_DRAFT_LIST_ID = os.getenv("TRELLO_DRAFT_LIST_ID", "")
    TRELLO_BACKLOG_LIST_ID = os.getenv("TRELLO_BACKLOG_LIST_ID", "")
    TRELLO_BLOCKED_LIST_ID = os.getenv("TRELLO_BLOCKED_LIST_ID", "")
    TRELLO_IN_PROGRESS_LIST_ID = os.getenv("TRELLO_IN_PROGRESS_LIST_ID", "")
    TRELLO_REVIEW_LIST_ID = os.getenv("TRELLO_REVIEW_LIST_ID", "")
    TRELLO_DONE_LIST_ID = os.getenv("TRELLO_DONE_LIST_ID", "")

    # ========================================
    # 번역 설정
    # ========================================
    TRANSLATE_CHANNELS = [
        ch.strip() for ch in os.getenv("TRANSLATE_CHANNELS", "").split(",") if ch.strip()
    ]
    TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "")
    TRANSLATE_CONTEXT_COUNT = _parse_int(os.getenv("TRANSLATE_CONTEXT_COUNT"), 0)
    TRANSLATE_API_KEY = os.getenv("TRANSLATE_API_KEY")

    TRANSLATE_SHOW_GLOSSARY = _parse_bool(os.getenv("TRANSLATE_SHOW_GLOSSARY"), False)
    TRANSLATE_SHOW_COST = _parse_bool(os.getenv("TRANSLATE_SHOW_COST"), False)
    TRANSLATE_DEBUG_CHANNEL = os.getenv("TRANSLATE_DEBUG_CHANNEL", "")

    # ========================================
    # Gemini 설정 (이미지 생성)
    # ========================================
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-image-preview")

    # ========================================
    # 실행 트리거 설정
    # ========================================
    EXECUTE_EMOJI = os.getenv("EXECUTE_EMOJI", "rocket")

    # ========================================
    # 경로 설정 (런타임에 cwd 기준 계산)
    # ========================================
    @staticmethod
    def get_log_path() -> str:
        """로그 경로"""
        return _get_path("LOG_PATH", "logs")

    @staticmethod
    def get_session_path() -> str:
        """세션 경로"""
        return _get_path("SESSION_PATH", "sessions")

    @staticmethod
    def get_glossary_path() -> str:
        """용어집 경로 (번역 시 고유명사 참조)"""
        return _get_path("GLOSSARY_PATH", "eb_lore/content/glossary.yaml")

    @staticmethod
    def get_narrative_path() -> str:
        """대사 데이터 경로"""
        return _get_path("NARRATIVE_PATH", "eb_narrative/narrative")

    @staticmethod
    def get_search_index_path() -> str:
        """검색 인덱스 경로"""
        return _get_path("SEARCH_INDEX_PATH", "internal/index/dialogues")

    @staticmethod
    def get_web_cache_path() -> str:
        """웹 콘텐츠 캐시 경로"""
        return _get_path("WEB_CACHE_PATH", ".local/cache/web")

    # ========================================
    # 검증
    # ========================================
    _REQUIRED_VARS = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"]

    @classmethod
    def validate(cls) -> None:
        """필수 환경변수 검증

        필수 환경변수가 누락된 경우 ConfigurationError를 발생시킵니다.

        Raises:
            ConfigurationError: 필수 환경변수 누락 시
        """
        missing = []
        for var in cls._REQUIRED_VARS:
            value = getattr(cls, var, None)
            if not value:
                missing.append(var)

        if missing:
            raise ConfigurationError(missing)
