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
        "admin": [
            "Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite",
            "mcp__seosoyoung-attach__slack_attach_file",
            "mcp__seosoyoung-attach__slack_get_context",
            "mcp__seosoyoung-attach__slack_post_message",
            "mcp__seosoyoung-attach__slack_download_thread_files",
            "mcp__seosoyoung-attach__slack_generate_image",
        ],
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
    TRELLO_DM_TARGET_USER_ID = os.getenv("TRELLO_DM_TARGET_USER_ID", "")

    # ========================================
    # 번역 설정
    # ========================================
    TRANSLATE_CHANNELS = [
        ch.strip() for ch in os.getenv("TRANSLATE_CHANNELS", "").split(",") if ch.strip()
    ]
    TRANSLATE_BACKEND = os.getenv("TRANSLATE_BACKEND", "anthropic")  # "anthropic" | "openai"
    TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "")
    TRANSLATE_OPENAI_MODEL = os.getenv("TRANSLATE_OPENAI_MODEL", "gpt-5-mini")
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
    # Observational Memory 설정
    # ========================================
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OM_MODEL = os.getenv("OM_MODEL", "gpt-4.1-mini")
    OM_ENABLED = _parse_bool(os.getenv("OM_ENABLED"), True)
    OM_DEBUG_CHANNEL = os.getenv("OM_DEBUG_CHANNEL", "")
    OM_REFLECTION_THRESHOLD = _parse_int(os.getenv("OM_REFLECTION_THRESHOLD"), 20000)
    OM_OBSERVATION_THRESHOLD = _parse_int(
        os.getenv("OM_OBSERVATION_THRESHOLD"), 30000
    )  # deprecated: 매턴 호출로 변경됨. agent_runner 하위 호환용으로 유지.
    OM_MAX_OBSERVATION_TOKENS = _parse_int(
        os.getenv("OM_MAX_OBSERVATION_TOKENS"), 30000
    )
    OM_MIN_TURN_TOKENS = _parse_int(os.getenv("OM_MIN_TURN_TOKENS"), 200)
    OM_PROMOTER_MODEL = os.getenv("OM_PROMOTER_MODEL", "gpt-5.2")
    OM_PROMOTION_THRESHOLD = _parse_int(os.getenv("OM_PROMOTION_THRESHOLD"), 5000)
    OM_PERSISTENT_COMPACTION_THRESHOLD = _parse_int(
        os.getenv("OM_PERSISTENT_COMPACTION_THRESHOLD"), 15000
    )
    OM_PERSISTENT_COMPACTION_TARGET = _parse_int(
        os.getenv("OM_PERSISTENT_COMPACTION_TARGET"), 8000
    )

    # ========================================
    # Channel Observer 설정
    # ========================================
    CHANNEL_OBSERVER_ENABLED = _parse_bool(os.getenv("CHANNEL_OBSERVER_ENABLED"), False)
    CHANNEL_OBSERVER_CHANNELS = [
        ch.strip()
        for ch in os.getenv("CHANNEL_OBSERVER_CHANNELS", "").split(",")
        if ch.strip()
    ]
    CHANNEL_OBSERVER_API_KEY = os.getenv("CHANNEL_OBSERVER_API_KEY") or os.getenv("OPENAI_API_KEY")
    CHANNEL_OBSERVER_MODEL = os.getenv("CHANNEL_OBSERVER_MODEL", "gpt-5-mini")
    CHANNEL_OBSERVER_COMPRESSOR_MODEL = os.getenv("CHANNEL_OBSERVER_COMPRESSOR_MODEL", "gpt-5.2")
    CHANNEL_OBSERVER_THRESHOLD_A = _parse_int(
        os.getenv("CHANNEL_OBSERVER_THRESHOLD_A"), 150
    )
    CHANNEL_OBSERVER_THRESHOLD_B = _parse_int(
        os.getenv("CHANNEL_OBSERVER_THRESHOLD_B"), 5000
    )
    # deprecated: THRESHOLD_A로 대체
    CHANNEL_OBSERVER_BUFFER_THRESHOLD = _parse_int(
        os.getenv("CHANNEL_OBSERVER_BUFFER_THRESHOLD"), 150
    )
    CHANNEL_OBSERVER_DIGEST_MAX_TOKENS = _parse_int(
        os.getenv("CHANNEL_OBSERVER_DIGEST_MAX_TOKENS"), 10000
    )
    CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS = _parse_int(
        os.getenv("CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS"), 5000
    )
    CHANNEL_OBSERVER_INTERVENTION_THRESHOLD = float(
        os.getenv("CHANNEL_OBSERVER_INTERVENTION_THRESHOLD", "0.3")
    )
    CHANNEL_OBSERVER_PERIODIC_SEC = _parse_int(
        os.getenv("CHANNEL_OBSERVER_PERIODIC_SEC"), 300
    )
    CHANNEL_OBSERVER_TRIGGER_WORDS = [
        w.strip()
        for w in os.getenv("CHANNEL_OBSERVER_TRIGGER_WORDS", "").split(",")
        if w.strip()
    ]
    CHANNEL_OBSERVER_DEBUG_CHANNEL = os.getenv(
        "CHANNEL_OBSERVER_DEBUG_CHANNEL", os.getenv("OM_DEBUG_CHANNEL", "")
    )

    # ========================================
    # 컨텍스트 사용량 표시 설정
    # ========================================
    SHOW_CONTEXT_USAGE = _parse_bool(os.getenv("SHOW_CONTEXT_USAGE"), False)

    # ========================================
    # 실행 트리거 설정
    # ========================================
    EXECUTE_EMOJI = os.getenv("EXECUTE_EMOJI", "rocket")

    # ========================================
    # 이모지 설정
    # ========================================
    # 번역 리액션 이모지 (슬랙 리액션으로 사용, 콜론 없이)
    EMOJI_TRANSLATE_PROGRESS = os.getenv("EMOJI_TRANSLATE_PROGRESS", "hourglass_flowing_sand")
    EMOJI_TRANSLATE_DONE = os.getenv("EMOJI_TRANSLATE_DONE", "ssy-happy")

    # 텍스트 이모지 (슬랙 메시지 텍스트용, 콜론 포함)
    EMOJI_TEXT_SESSION_START = os.getenv("EMOJI_TEXT_SESSION_START", ":ssy-surprised:")
    EMOJI_TEXT_LTM_INJECT = os.getenv("EMOJI_TEXT_LTM_INJECT", ":ssy-thinking:")
    EMOJI_TEXT_NEW_OBS_INJECT = os.getenv("EMOJI_TEXT_NEW_OBS_INJECT", ":ssy-curious:")
    EMOJI_TEXT_SESSION_OBS_INJECT = os.getenv("EMOJI_TEXT_SESSION_OBS_INJECT", ":ssy-thinking:")
    EMOJI_TEXT_CHANNEL_OBS_INJECT = os.getenv("EMOJI_TEXT_CHANNEL_OBS_INJECT", ":ssy-curious:")
    EMOJI_TEXT_RESTART_TROUBLE = os.getenv("EMOJI_TEXT_RESTART_TROUBLE", ":ssy-troubled:")
    EMOJI_TEXT_OBS_COMPLETE = os.getenv("EMOJI_TEXT_OBS_COMPLETE", ":ssy-happy:")
    EMOJI_TEXT_INTERVENTION_ERROR = os.getenv("EMOJI_TEXT_INTERVENTION_ERROR", ":ssy-troubled:")

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

    @staticmethod
    def get_memory_path() -> str:
        """관찰 로그 저장 경로"""
        return _get_path("MEMORY_PATH", "memory")

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
