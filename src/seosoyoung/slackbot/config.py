"""설정 관리

카테고리별로 구분된 설정을 관리합니다.
- 경로 설정: get_*() 메서드 (cwd 기준 계산 필요)
- 그 외 설정: @dataclass 하위 그룹 (모듈 로드 시 평가)
"""

import os
from dataclasses import dataclass, field
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


@dataclass
class SlackConfig:
    """Slack 연결 설정"""

    bot_token: str | None = os.getenv("SLACK_BOT_TOKEN")
    app_token: str | None = os.getenv("SLACK_APP_TOKEN")
    bot_user_id: str | None = None  # 런타임에 auth.test()로 설정
    notify_channel: str = os.getenv("NOTIFY_CHANNEL", "")


@dataclass
class AuthConfig:
    """권한 설정"""

    allowed_users: list[str] = field(
        default_factory=lambda: os.getenv("ALLOWED_USERS", "").split(",")
    )
    admin_users: list[str] = field(
        default_factory=lambda: [
            u.strip() for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()
        ]
    )
    role_tools: dict = field(
        default_factory=lambda: {
            "admin": None,  # None = 모든 도구 허용 (MCP 포함)
            "viewer": ["Read", "Glob", "Grep"],
        }
    )


@dataclass
class TrelloConfig:
    """Trello 설정"""

    api_key: str = os.getenv("TRELLO_API_KEY", "")
    token: str = os.getenv("TRELLO_TOKEN", "")
    board_id: str = os.getenv("TRELLO_BOARD_ID", "")
    notify_channel: str = os.getenv("TRELLO_NOTIFY_CHANNEL", "")
    watch_lists: dict = field(
        default_factory=lambda: {"to_go": os.getenv("TRELLO_TO_GO_LIST_ID", "")}
    )
    draft_list_id: str = os.getenv("TRELLO_DRAFT_LIST_ID", "")
    backlog_list_id: str = os.getenv("TRELLO_BACKLOG_LIST_ID", "")
    blocked_list_id: str = os.getenv("TRELLO_BLOCKED_LIST_ID", "")
    in_progress_list_id: str = os.getenv("TRELLO_IN_PROGRESS_LIST_ID", "")
    review_list_id: str = os.getenv("TRELLO_REVIEW_LIST_ID", "")
    done_list_id: str = os.getenv("TRELLO_DONE_LIST_ID", "")
    dm_target_user_id: str = os.getenv("TRELLO_DM_TARGET_USER_ID", "")
    polling_debug: bool = _parse_bool(os.getenv("TRELLO_POLLING_DEBUG"), False)


@dataclass
class TranslateConfig:
    """번역 설정"""

    channels: list[str] = field(
        default_factory=lambda: [
            ch.strip()
            for ch in os.getenv("TRANSLATE_CHANNELS", "").split(",")
            if ch.strip()
        ]
    )
    backend: str = os.getenv("TRANSLATE_BACKEND", "anthropic")
    model: str = os.getenv("TRANSLATE_MODEL", "")
    openai_model: str = os.getenv("TRANSLATE_OPENAI_MODEL", "gpt-5-mini")
    api_key: str | None = os.getenv("TRANSLATE_API_KEY")
    context_count: int = _parse_int(os.getenv("TRANSLATE_CONTEXT_COUNT"), 0)
    show_glossary: bool = _parse_bool(os.getenv("TRANSLATE_SHOW_GLOSSARY"), False)
    show_cost: bool = _parse_bool(os.getenv("TRANSLATE_SHOW_COST"), False)
    debug_channel: str = os.getenv("TRANSLATE_DEBUG_CHANNEL", "")


@dataclass
class GeminiConfig:
    """Gemini 설정 (이미지 생성)"""

    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3-pro-image-preview")


@dataclass
class OMConfig:
    """Observational Memory 설정"""

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    model: str = os.getenv("OM_MODEL", "gpt-4.1-mini")
    enabled: bool = _parse_bool(os.getenv("OM_ENABLED"), True)
    debug_channel: str = os.getenv("OM_DEBUG_CHANNEL", "")
    reflection_threshold: int = _parse_int(os.getenv("OM_REFLECTION_THRESHOLD"), 20000)
    observation_threshold: int = _parse_int(
        os.getenv("OM_OBSERVATION_THRESHOLD"), 30000
    )  # deprecated: 매턴 호출로 변경됨. agent_runner 하위 호환용으로 유지.
    max_observation_tokens: int = _parse_int(
        os.getenv("OM_MAX_OBSERVATION_TOKENS"), 30000
    )
    min_turn_tokens: int = _parse_int(os.getenv("OM_MIN_TURN_TOKENS"), 200)
    promoter_model: str = os.getenv("OM_PROMOTER_MODEL", "gpt-5.2")
    promotion_threshold: int = _parse_int(os.getenv("OM_PROMOTION_THRESHOLD"), 5000)
    persistent_compaction_threshold: int = _parse_int(
        os.getenv("OM_PERSISTENT_COMPACTION_THRESHOLD"), 15000
    )
    persistent_compaction_target: int = _parse_int(
        os.getenv("OM_PERSISTENT_COMPACTION_TARGET"), 8000
    )


@dataclass
class ChannelObserverConfig:
    """Channel Observer 설정"""

    enabled: bool = _parse_bool(os.getenv("CHANNEL_OBSERVER_ENABLED"), False)
    channels: list[str] = field(
        default_factory=lambda: [
            ch.strip()
            for ch in os.getenv("CHANNEL_OBSERVER_CHANNELS", "").split(",")
            if ch.strip()
        ]
    )
    api_key: str | None = (
        os.getenv("CHANNEL_OBSERVER_API_KEY") or os.getenv("OPENAI_API_KEY")
    )
    model: str = os.getenv("CHANNEL_OBSERVER_MODEL", "gpt-5-mini")
    compressor_model: str = os.getenv(
        "CHANNEL_OBSERVER_COMPRESSOR_MODEL", "gpt-5.2"
    )
    threshold_a: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_THRESHOLD_A"), 150
    )
    threshold_b: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_THRESHOLD_B"), 5000
    )
    # deprecated: threshold_a로 대체
    buffer_threshold: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_BUFFER_THRESHOLD"), 150
    )
    digest_max_tokens: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_DIGEST_MAX_TOKENS"), 10000
    )
    digest_target_tokens: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS"), 5000
    )
    intervention_threshold: float = _parse_float(
        os.getenv("CHANNEL_OBSERVER_INTERVENTION_THRESHOLD"), 0.18
    )
    periodic_sec: int = _parse_int(
        os.getenv("CHANNEL_OBSERVER_PERIODIC_SEC"), 300
    )
    trigger_words: list[str] = field(
        default_factory=lambda: [
            w.strip()
            for w in os.getenv("CHANNEL_OBSERVER_TRIGGER_WORDS", "").split(",")
            if w.strip()
        ]
    )
    debug_channel: str = os.getenv(
        "CHANNEL_OBSERVER_DEBUG_CHANNEL", os.getenv("OM_DEBUG_CHANNEL", "")
    )


@dataclass
class ClaudeConfig:
    """Claude 실행 모드 설정"""

    execution_mode: str = os.getenv("CLAUDE_EXECUTION_MODE", "local")
    soul_url: str = os.getenv("SEOSOYOUNG_SOUL_URL", "http://localhost:3105")
    soul_token: str = os.getenv("SEOSOYOUNG_SOUL_TOKEN", "")
    soul_client_id: str = os.getenv("SEOSOYOUNG_SOUL_CLIENT_ID", "seosoyoung_bot")


@dataclass
class EmojiConfig:
    """이모지 설정"""

    execute: str = os.getenv("EXECUTE_EMOJI", "rocket")
    # 번역 리액션 이모지 (슬랙 리액션으로 사용, 콜론 없이)
    translate_progress: str = os.getenv(
        "EMOJI_TRANSLATE_PROGRESS", "hourglass_flowing_sand"
    )
    translate_done: str = os.getenv("EMOJI_TRANSLATE_DONE", "ssy-happy")
    # 텍스트 이모지 (슬랙 메시지 텍스트용, 콜론 포함)
    text_session_start: str = os.getenv("EMOJI_TEXT_SESSION_START", ":ssy-surprised:")
    text_ltm_inject: str = os.getenv("EMOJI_TEXT_LTM_INJECT", ":ssy-thinking:")
    text_new_obs_inject: str = os.getenv("EMOJI_TEXT_NEW_OBS_INJECT", ":ssy-curious:")
    text_session_obs_inject: str = os.getenv(
        "EMOJI_TEXT_SESSION_OBS_INJECT", ":ssy-thinking:"
    )
    text_channel_obs_inject: str = os.getenv(
        "EMOJI_TEXT_CHANNEL_OBS_INJECT", ":ssy-curious:"
    )
    text_restart_trouble: str = os.getenv(
        "EMOJI_TEXT_RESTART_TROUBLE", ":ssy-troubled:"
    )
    text_obs_complete: str = os.getenv("EMOJI_TEXT_OBS_COMPLETE", ":ssy-happy:")
    text_intervention_error: str = os.getenv(
        "EMOJI_TEXT_INTERVENTION_ERROR", ":ssy-troubled:"
    )


class Config:
    """애플리케이션 설정

    설정 접근 방식:
    - 경로 관련: get_*() 메서드 (런타임에 cwd 기준 계산)
    - 그 외: 하위 설정 그룹 (모듈 로드 시 평가)
    """

    debug: bool = _parse_bool(os.getenv("DEBUG"), False)

    slack = SlackConfig()
    auth = AuthConfig()
    trello = TrelloConfig()
    translate = TranslateConfig()
    gemini = GeminiConfig()
    om = OMConfig()
    channel_observer = ChannelObserverConfig()
    claude = ClaudeConfig()
    emoji = EmojiConfig()

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
    @classmethod
    def validate(cls) -> None:
        """필수 환경변수 검증

        필수 환경변수가 누락된 경우 ConfigurationError를 발생시킵니다.

        Raises:
            ConfigurationError: 필수 환경변수 누락 시
        """
        missing = []
        if not cls.slack.bot_token:
            missing.append("SLACK_BOT_TOKEN")
        if not cls.slack.app_token:
            missing.append("SLACK_APP_TOKEN")

        if missing:
            raise ConfigurationError(missing)
