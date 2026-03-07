"""MCP 서버 설정"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

WORKSPACE_ROOT = os.getenv(
    "SOYOUNG_WORKSPACE",
    str(Path(__file__).resolve().parents[5]),
)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
