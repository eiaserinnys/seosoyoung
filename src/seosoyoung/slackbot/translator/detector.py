"""언어 감지 모듈

Unicode 블록 기반으로 한글/영어를 감지합니다.
"""

from enum import Enum


class Language(Enum):
    KOREAN = "ko"
    ENGLISH = "en"


def is_korean_char(char: str) -> bool:
    """한글 문자인지 확인 (한글 자모, 음절 모두 포함)"""
    code = ord(char)
    # 한글 음절: U+AC00 ~ U+D7A3
    # 한글 자모: U+1100 ~ U+11FF
    # 한글 호환 자모: U+3130 ~ U+318F
    return (
        (0xAC00 <= code <= 0xD7A3) or
        (0x1100 <= code <= 0x11FF) or
        (0x3130 <= code <= 0x318F)
    )


def detect_language(text: str, threshold: float = 0.3) -> Language:
    """텍스트의 언어를 감지

    Args:
        text: 감지할 텍스트
        threshold: 한글 비율 임계값 (기본 30%)

    Returns:
        Language.KOREAN 또는 Language.ENGLISH
    """
    if not text:
        return Language.ENGLISH

    # 공백, 숫자, 특수문자 제외한 문자만 카운트
    total_chars = 0
    korean_chars = 0

    for char in text:
        if char.isalpha():  # 알파벳/한글 등 문자만
            total_chars += 1
            if is_korean_char(char):
                korean_chars += 1

    if total_chars == 0:
        return Language.ENGLISH

    korean_ratio = korean_chars / total_chars
    return Language.KOREAN if korean_ratio > threshold else Language.ENGLISH
