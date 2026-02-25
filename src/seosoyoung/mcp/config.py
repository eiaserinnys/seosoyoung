"""MCP 서버 설정"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

WORKSPACE_ROOT = os.getenv(
    "SOYOUNG_WORKSPACE",
    str(Path(__file__).resolve().parents[5]),
)

ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".yaml", ".yml", ".json", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".xlsx", ".xls", ".html",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
