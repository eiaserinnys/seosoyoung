"""설정 관리

카테고리별로 구분된 설정을 관리합니다.
- 경로 설정: get_*() 메서드 (cwd 기준 계산 필요)
- 그 외 설정: @dataclass 하위 그룹 (모듈 로드 시 평가)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))


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


@dataclass
class SlackConfig:
    """Slack 연결 설정"""

    bot_token: str | None = os.getenv("SLACK_BOT_TOKEN")
    app_token: str | None = os.getenv("SLACK_APP_TOKEN")
    bot_user_id: str | None = None  # 런타임에 auth.test()로 설정
    operator_user_id: str = os.environ["OPERATOR_USER_ID"]
    # 미설정 시 빈 문자열 → 슬랙 버튼 미표시
    workspace_url: str = os.getenv("SLACK_WORKSPACE_URL", "")


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
class GeminiConfig:
    """Gemini 설정 (이미지 생성)"""

    api_key: str | None = os.getenv("GEMINI_API_KEY")
    model: str = os.environ["GEMINI_MODEL"]


@dataclass
class ClaudeConfig:
    """Claude 실행 모드 설정

    remote 모드에서 Soulstream 서버(독립 soul-server)에 연결합니다.
    per-session 아키텍처: agent_session_id가 유일한 식별자.
    """

    soul_url: str = os.environ["SEOSOYOUNG_SOUL_URL"]
    soul_token: str = os.environ["SEOSOYOUNG_SOUL_TOKEN"]
    dashboard_url: str = os.environ["SOUL_DASHBOARD_URL"]
    credential_alert_channel: str = os.getenv("CREDENTIAL_ALERT_CHANNEL", "")
    agent_id: str = os.getenv("SEOSOYOUNG_AGENT_ID", "")
    # SEOSOYOUNG_AGENT_ID: soul-server agents.yaml의 에이전트 ID.
    # 설정 시 모든 세션 요청에 해당 프로필을 기본값으로 사용.
    # 미설정(빈 문자열) 시 기존 동작(profile=None) 유지 (하위 호환).


@dataclass
class EmojiConfig:
    """이모지 설정"""

    execute: str = os.environ["EXECUTE_EMOJI"]
    # 번역 리액션 이모지 (슬랙 리액션으로 사용, 콜론 없이)
    translate_progress: str = os.environ["EMOJI_TRANSLATE_PROGRESS"]
    translate_done: str = os.environ["EMOJI_TRANSLATE_DONE"]
    # 텍스트 이모지 (슬랙 메시지 텍스트용, 콜론 포함)
    text_session_start: str = os.environ["EMOJI_TEXT_SESSION_START"]
    text_ltm_inject: str = os.environ["EMOJI_TEXT_LTM_INJECT"]
    text_new_obs_inject: str = os.environ["EMOJI_TEXT_NEW_OBS_INJECT"]
    text_session_obs_inject: str = os.environ["EMOJI_TEXT_SESSION_OBS_INJECT"]
    text_channel_obs_inject: str = os.environ["EMOJI_TEXT_CHANNEL_OBS_INJECT"]
    text_restart_trouble: str = os.environ["EMOJI_TEXT_RESTART_TROUBLE"]
    text_obs_complete: str = os.environ["EMOJI_TEXT_OBS_COMPLETE"]
    text_intervention_error: str = os.environ["EMOJI_TEXT_INTERVENTION_ERROR"]


@dataclass
class BotIdentityConfig:
    """봇 정체성 문구 설정 (기본값: 일반적인 슬랙봇 문구)"""

    name: str = field(default_factory=lambda: os.environ.get("BOT_NAME", "봇"))
    mention_name: str = field(default_factory=lambda: os.environ.get("BOT_MENTION_NAME", "@봇"))
    thinking_text: str = field(default_factory=lambda: os.environ.get("BOT_THINKING_TEXT", "*생각합니다...*"))
    startup_message: str = field(
        default_factory=lambda: os.environ.get("BOT_STARTUP_MESSAGE", "안녕하세요, 봇이 시작되었습니다.")
    )
    shutdown_message: str = field(
        default_factory=lambda: os.environ.get("BOT_SHUTDOWN_MESSAGE", "다음에 또 뵙겠습니다, 안녕히 계세요.")
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
    gemini = GeminiConfig()
    claude = ClaudeConfig()
    emoji = EmojiConfig()
    bot = BotIdentityConfig()

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
