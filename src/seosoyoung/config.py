"""설정 관리"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Slack
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

    # Paths
    EB_RENPY_PATH = os.getenv("EB_RENPY_PATH", r"D:\soyoung_root\eb_renpy")
    LOG_PATH = os.getenv("LOG_PATH", r"D:\soyoung_root\seosoyoung_runtime\logs")
    SESSION_PATH = os.getenv("SESSION_PATH", r"D:\soyoung_root\seosoyoung_runtime\sessions")

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
