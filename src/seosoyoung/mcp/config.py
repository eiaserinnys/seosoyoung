"""MCP 서버 설정"""

import os
from pathlib import Path

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
NPC_CLAUDE_API_KEY = os.getenv("NPC_CLAUDE_API_KEY", "")

WORKSPACE_ROOT = str(Path(__file__).resolve().parents[4])

ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".yaml", ".yml", ".json", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".xlsx", ".xls", ".html",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
