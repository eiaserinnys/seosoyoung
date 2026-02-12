"""프롬프트 파일 로더

외부 텍스트 파일에서 프롬프트를 로드합니다.
프롬프트 파일은 memory/prompt_files/ 디렉토리에 저장됩니다.
"""

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).parent / "prompt_files"


def load_prompt(filename: str) -> str:
    """프롬프트 파일을 로드합니다.

    Args:
        filename: prompt_files/ 디렉토리 내 파일명

    Returns:
        프롬프트 텍스트

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때
    """
    path = PROMPT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일 없음: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=32)
def load_prompt_cached(filename: str) -> str:
    """프롬프트 파일을 캐시하여 로드합니다.

    프로세스 수명 동안 한 번만 파일을 읽습니다.
    프롬프트 파일이 변경되면 프로세스를 재시작해야 합니다.

    Args:
        filename: prompt_files/ 디렉토리 내 파일명

    Returns:
        프롬프트 텍스트
    """
    return load_prompt(filename)
