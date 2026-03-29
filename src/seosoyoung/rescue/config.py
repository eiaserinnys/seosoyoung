"""rescue-bot 환경변수 설정

메인 봇과 완전 독립된 별도 Slack App 토큰을 사용합니다.
"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))


class RescueConfig:
    """rescue-bot 설정"""

    # Slack 토큰 (별도 Slack App)
    SLACK_BOT_TOKEN: str = os.environ["RESCUE_SLACK_BOT_TOKEN"]
    SLACK_APP_TOKEN: str = os.environ["RESCUE_SLACK_APP_TOKEN"]

    # 봇 사용자 ID (런타임에 auth.test()로 설정)
    BOT_USER_ID: str | None = None

    @classmethod
    def validate(cls) -> None:
        """필수 환경변수 검증"""
        missing = []
        if not cls.SLACK_BOT_TOKEN:
            missing.append("RESCUE_SLACK_BOT_TOKEN")
        if not cls.SLACK_APP_TOKEN:
            missing.append("RESCUE_SLACK_APP_TOKEN")
        if missing:
            raise RuntimeError(
                f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing)}"
            )

    @staticmethod
    def get_working_dir() -> Path:
        """Claude Code SDK 작업 디렉토리 (env의 WORKSPACE_DIR 우선, 없으면 cwd)"""
        workspace_dir = os.environ.get("WORKSPACE_DIR")
        if workspace_dir:
            return Path(workspace_dir)
        return Path.cwd()
