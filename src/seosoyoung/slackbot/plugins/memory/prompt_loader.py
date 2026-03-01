"""프롬프트 파일 로더

외부 텍스트 파일에서 프롬프트를 로드합니다.

검색 순서:
1. 환경변수로 지정된 개별 파일 (OM_PROMPT_DIR / CHANNEL_PROMPT_DIR)
2. 환경변수로 지정된 공통 디렉토리 (PROMPT_FILES_DIR)
3. 배포본 기본 경로 (memory/prompt_files/)

비워두거나 미설정하면 배포본에 포함된 기본 경로를 사용합니다.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# 배포본 기본 경로
DEFAULT_PROMPT_DIR = Path(__file__).parent / "prompt_files"

# 환경변수에서 오버라이드 경로를 결정하는 접두사-환경변수 매핑
_PREFIX_ENV_MAP = {
    "om_": "OM_PROMPT_DIR",
    "channel_": "CHANNEL_PROMPT_DIR",
    "digest_": "CHANNEL_PROMPT_DIR",
    "intervention_": "CHANNEL_PROMPT_DIR",
}


def _resolve_prompt_path(filename: str) -> Path:
    """프롬프트 파일의 실제 경로를 결정합니다.

    검색 순서:
    1. 파일명 접두사에 따른 개별 디렉토리 환경변수
    2. 공통 디렉토리 환경변수 (PROMPT_FILES_DIR)
    3. 배포본 기본 경로

    Args:
        filename: 프롬프트 파일명

    Returns:
        해결된 파일 경로
    """
    # 1. 접두사별 개별 디렉토리
    for prefix, env_var in _PREFIX_ENV_MAP.items():
        if filename.startswith(prefix):
            env_dir = os.getenv(env_var, "").strip()
            if env_dir:
                candidate = Path(env_dir) / filename
                if candidate.exists():
                    return candidate
            break

    # 2. 공통 디렉토리
    common_dir = os.getenv("PROMPT_FILES_DIR", "").strip()
    if common_dir:
        candidate = Path(common_dir) / filename
        if candidate.exists():
            return candidate

    # 3. 배포본 기본 경로
    return DEFAULT_PROMPT_DIR / filename


# 하위 호환: 기존 코드에서 PROMPT_DIR을 참조하는 경우를 위해 유지
PROMPT_DIR = DEFAULT_PROMPT_DIR


def load_prompt(filename: str) -> str:
    """프롬프트 파일을 로드합니다.

    Args:
        filename: 프롬프트 파일명

    Returns:
        프롬프트 텍스트

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때
    """
    path = _resolve_prompt_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일 없음: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=32)
def load_prompt_cached(filename: str) -> str:
    """프롬프트 파일을 캐시하여 로드합니다.

    프로세스 수명 동안 한 번만 파일을 읽습니다.
    프롬프트 파일이 변경되면 프로세스를 재시작해야 합니다.

    Args:
        filename: 프롬프트 파일명

    Returns:
        프롬프트 텍스트
    """
    return load_prompt(filename)
