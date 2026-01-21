"""로깅 설정 모듈"""

import logging
from datetime import datetime
from pathlib import Path

from seosoyoung.config import Config


def setup_logging() -> logging.Logger:
    """로깅 설정 및 로거 반환"""
    log_dir = Path(Config.get_log_path())
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    # urllib3 HTTP 요청 로그 제어
    # TRELLO_POLLING_DEBUG=true일 때만 DEBUG 로그 출력
    if not Config.TRELLO_POLLING_DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(__name__)
