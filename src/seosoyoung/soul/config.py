"""
Seosoyoung Soul - Configuration

환경변수 기반 설정 관리.
"""

import os
import logging
import sys
from functools import lru_cache
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_config_logger = logging.getLogger(__name__)


def _safe_int(value: str, default: int, name: str) -> int:
    """환경변수를 안전하게 int로 변환

    Args:
        value: 변환할 문자열
        default: 변환 실패 시 기본값
        name: 환경변수 이름 (로깅용)

    Returns:
        변환된 int 값 또는 기본값
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        _config_logger.warning(f"Invalid {name} value '{value}', using default: {default}")
        return default


def _safe_float(value: str, default: float, name: str) -> float:
    """환경변수를 안전하게 float로 변환

    Args:
        value: 변환할 문자열
        default: 변환 실패 시 기본값
        name: 환경변수 이름 (로깅용)

    Returns:
        변환된 float 값 또는 기본값
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        _config_logger.warning(f"Invalid {name} value '{value}', using default: {default}")
        return default


@dataclass
class Settings:
    """애플리케이션 설정"""

    # 서비스 정보
    service_name: str = "seosoyoung-soul"
    version: str = "0.1.0"
    environment: str = "development"  # development, staging, production

    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 3105  # supervisor 포트 체계에 맞춤

    # 인증
    claude_service_token: str = ""

    # Claude Code 설정
    anthropic_api_key: str = ""
    workspace_dir: str = "D:/soyoung_root/slackbot_workspace"

    # 리소스 제한
    max_concurrent_sessions: int = 3
    session_timeout_seconds: int = 1800  # 30분

    # Runner Pool 설정
    runner_pool_max_size: int = 5           # idle pool 최대 크기 (session + generic 합산)
    runner_pool_idle_ttl: float = 300.0     # 유휴 runner TTL (초)
    runner_pool_pre_warm: int = 2           # 기동 시 예열할 generic runner 수
    runner_pool_maintenance_interval: float = 60.0  # 유지보수 루프 실행 간격 (초)
    runner_pool_min_generic: int = 1        # generic pool 최소 유지 수량

    # 로깅
    log_level: str = "INFO"
    log_format: str = "json"  # json, text

    # 헬스 체크
    health_check_interval: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        """환경변수에서 설정 로드"""
        return cls(
            service_name=os.getenv("SERVICE_NAME", cls.service_name),
            version=os.getenv("SERVICE_VERSION", cls.version),
            environment=os.getenv("ENVIRONMENT", cls.environment),
            host=os.getenv("HOST", cls.host),
            port=_safe_int(os.getenv("PORT", str(cls.port)), cls.port, "PORT"),
            claude_service_token=os.getenv("CLAUDE_SERVICE_TOKEN", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            workspace_dir=os.getenv("WORKSPACE_DIR", cls.workspace_dir),
            max_concurrent_sessions=_safe_int(
                os.getenv("MAX_CONCURRENT_SESSIONS", str(cls.max_concurrent_sessions)),
                cls.max_concurrent_sessions,
                "MAX_CONCURRENT_SESSIONS"
            ),
            session_timeout_seconds=_safe_int(
                os.getenv("SESSION_TIMEOUT_SECONDS", str(cls.session_timeout_seconds)),
                cls.session_timeout_seconds,
                "SESSION_TIMEOUT_SECONDS"
            ),
            runner_pool_max_size=_safe_int(
                os.getenv("RUNNER_POOL_MAX_SIZE", str(cls.runner_pool_max_size)),
                cls.runner_pool_max_size,
                "RUNNER_POOL_MAX_SIZE"
            ),
            runner_pool_idle_ttl=_safe_float(
                os.getenv("RUNNER_POOL_IDLE_TTL", str(cls.runner_pool_idle_ttl)),
                cls.runner_pool_idle_ttl,
                "RUNNER_POOL_IDLE_TTL"
            ),
            runner_pool_pre_warm=_safe_int(
                os.getenv("RUNNER_POOL_PRE_WARM", str(cls.runner_pool_pre_warm)),
                cls.runner_pool_pre_warm,
                "RUNNER_POOL_PRE_WARM"
            ),
            runner_pool_maintenance_interval=_safe_float(
                os.getenv("RUNNER_POOL_MAINTENANCE_INTERVAL", str(cls.runner_pool_maintenance_interval)),
                cls.runner_pool_maintenance_interval,
                "RUNNER_POOL_MAINTENANCE_INTERVAL"
            ),
            runner_pool_min_generic=_safe_int(
                os.getenv("RUNNER_POOL_MIN_GENERIC", str(cls.runner_pool_min_generic)),
                cls.runner_pool_min_generic,
                "RUNNER_POOL_MIN_GENERIC"
            ),
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
            log_format=os.getenv("LOG_FORMAT", cls.log_format),
            health_check_interval=_safe_int(
                os.getenv("HEALTH_CHECK_INTERVAL", str(cls.health_check_interval)),
                cls.health_check_interval,
                "HEALTH_CHECK_INTERVAL"
            ),
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    return Settings.from_env()


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    """로깅 설정

    프로덕션: JSON 포맷 (구조화된 로그)
    개발: 텍스트 포맷 (가독성)
    """
    if settings is None:
        settings = get_settings()

    # 기존 핸들러 제거
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 로그 레벨 설정
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.log_format == "json" and settings.is_production:
        # JSON 포맷 (프로덕션)
        import json

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "service": settings.service_name,
                    "environment": settings.environment,
                }

                # 예외 정보 추가
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)

                # 추가 속성
                if hasattr(record, "extra"):
                    log_data.update(record.extra)

                return json.dumps(log_data, ensure_ascii=False)

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
    else:
        # 텍스트 포맷 (개발)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # uvicorn 로거 레벨 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(log_level)

    logger = logging.getLogger(settings.service_name)
    logger.setLevel(log_level)

    return logger
