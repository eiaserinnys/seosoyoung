"""설정 관리"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _get_path(env_var: str, default_subdir: str) -> str:
    """환경변수가 없으면 현재 경로 하위 폴더 반환"""
    env_value = os.getenv(env_var)
    if env_value:
        return env_value
    return str(Path.cwd() / default_subdir)


class Config:
    # Slack
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
    BOT_USER_ID: str | None = None  # 런타임에 auth.test()로 설정

    # Paths - 런타임에 평가 (환경변수 없으면 현재 경로 기준)
    @staticmethod
    def get_log_path() -> str:
        return _get_path("LOG_PATH", "logs")

    @staticmethod
    def get_session_path() -> str:
        return _get_path("SESSION_PATH", "sessions")

    # Claude
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    # Permissions
    ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
    ADMIN_USERS = [u.strip() for u in os.getenv("ADMIN_USERS", "").split(",") if u.strip()]

    # 역할별 도구 권한
    ROLE_TOOLS = {
        "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
        "viewer": ["Read", "Glob", "Grep"],
    }

    # Claude Code SDK 모드 (True: SDK 사용, False: CLI 사용)
    CLAUDE_USE_SDK = os.getenv("CLAUDE_USE_SDK", "false").lower() == "true"

    # Debug
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    TRELLO_POLLING_DEBUG = os.getenv("TRELLO_POLLING_DEBUG", "false").lower() == "true"

    # Notification
    NOTIFY_CHANNEL = os.getenv("NOTIFY_CHANNEL", "")

    # Trello
    TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
    TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
    TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")
    TRELLO_NOTIFY_CHANNEL = os.getenv("TRELLO_NOTIFY_CHANNEL", "")
    TRELLO_WATCH_LISTS = {
        "to_go": os.getenv("TRELLO_TO_GO_LIST_ID", ""),
    }
    TRELLO_BACKLOG_LIST_ID = os.getenv("TRELLO_BACKLOG_LIST_ID", "")
    TRELLO_IN_PROGRESS_LIST_ID = os.getenv("TRELLO_IN_PROGRESS_LIST_ID", "")
    TRELLO_REVIEW_LIST_ID = os.getenv("TRELLO_REVIEW_LIST_ID", "")
    TRELLO_DONE_LIST_ID = os.getenv("TRELLO_DONE_LIST_ID", "")

    # 번역 기능 설정
    # TRANSLATE_CHANNELS: 쉼표로 구분된 채널 ID 목록
    TRANSLATE_CHANNELS = [
        ch.strip() for ch in os.getenv("TRANSLATE_CHANNELS", "").split(",") if ch.strip()
    ]
    TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "")
    TRANSLATE_CONTEXT_COUNT = int(os.getenv("TRANSLATE_CONTEXT_COUNT", "0") or "0")
    TRANSLATE_API_KEY = os.getenv("TRANSLATE_API_KEY")  # 번역 전용 API 키

    # 번역 응답 표시 옵션
    TRANSLATE_SHOW_GLOSSARY = os.getenv("TRANSLATE_SHOW_GLOSSARY", "false").lower() == "true"
    TRANSLATE_SHOW_COST = os.getenv("TRANSLATE_SHOW_COST", "false").lower() == "true"

    # 번역 디버그 로그 채널 (비어있으면 비활성화)
    TRANSLATE_DEBUG_CHANNEL = os.getenv("TRANSLATE_DEBUG_CHANNEL", "")

    # 리액션 기반 실행 트리거 이모지 (슬랙 리액션 이름, 콜론 없이)
    EXECUTE_EMOJI = os.getenv("EXECUTE_EMOJI", "rocket")

    # 용어집 경로 (번역 시 고유명사 참조)
    @staticmethod
    def get_glossary_path() -> str:
        return _get_path("GLOSSARY_PATH", "eb_lore/content/glossary.yaml")

    # 대사 검색 관련 경로
    @staticmethod
    def get_narrative_path() -> str:
        """대사 데이터 경로 (eb_narrative/narrative)"""
        return _get_path("NARRATIVE_PATH", "eb_narrative/narrative")

    @staticmethod
    def get_search_index_path() -> str:
        """검색 인덱스 경로 (internal/index/dialogues)"""
        return _get_path("SEARCH_INDEX_PATH", "internal/index/dialogues")
