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
    ADMIN_USERS = [u.strip() for u in os.getenv("ADMIN_USERS", "eias").split(",") if u.strip()]

    # 역할별 도구 권한
    ROLE_TOOLS = {
        "admin": ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
        "viewer": ["Read", "Glob", "Grep"],
    }

    # Debug
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Notification
    NOTIFY_CHANNEL = os.getenv("NOTIFY_CHANNEL", "")
