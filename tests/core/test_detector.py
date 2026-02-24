"""언어 감지 모듈 테스트"""

import pytest
from seosoyoung.slackbot.translator.detector import detect_language, is_korean_char, Language


class TestIsKoreanChar:
    """한글 문자 감지 테스트"""

    def test_korean_syllable(self):
        """한글 음절 감지"""
        assert is_korean_char("가") is True
        assert is_korean_char("힣") is True
        assert is_korean_char("안") is True

    def test_korean_jamo(self):
        """한글 자모 감지"""
        assert is_korean_char("ㄱ") is True
        assert is_korean_char("ㅏ") is True

    def test_english(self):
        """영문 문자는 False"""
        assert is_korean_char("a") is False
        assert is_korean_char("Z") is False

    def test_number_and_symbol(self):
        """숫자와 기호는 False"""
        assert is_korean_char("1") is False
        assert is_korean_char("!") is False
        assert is_korean_char(" ") is False


class TestDetectLanguage:
    """언어 감지 테스트"""

    def test_korean_text(self):
        """한국어 텍스트 감지"""
        assert detect_language("안녕하세요") == Language.KOREAN
        assert detect_language("오늘 날씨가 좋네요") == Language.KOREAN
        assert detect_language("테스트입니다 123") == Language.KOREAN

    def test_english_text(self):
        """영어 텍스트 감지"""
        assert detect_language("Hello world") == Language.ENGLISH
        assert detect_language("How are you today?") == Language.ENGLISH
        assert detect_language("Test 123") == Language.ENGLISH

    def test_mixed_text_korean_majority(self):
        """한글이 많은 혼합 텍스트"""
        # 한글이 30% 이상이면 한국어
        assert detect_language("안녕하세요 Hello") == Language.KOREAN
        assert detect_language("테스트 test 입니다") == Language.KOREAN

    def test_mixed_text_english_majority(self):
        """영어가 많은 혼합 텍스트"""
        # 한글이 30% 미만이면 영어
        assert detect_language("Hello world 안녕") == Language.ENGLISH

    def test_empty_text(self):
        """빈 텍스트는 영어로 처리"""
        assert detect_language("") == Language.ENGLISH
        assert detect_language("   ") == Language.ENGLISH

    def test_only_numbers_and_symbols(self):
        """숫자와 기호만 있으면 영어로 처리"""
        assert detect_language("123 456") == Language.ENGLISH
        assert detect_language("!@#$%") == Language.ENGLISH

    def test_custom_threshold(self):
        """임계값 조절 테스트"""
        # "안녕 Hello World" -> 한글 2자, 영문 10자 = 2/12 ≈ 16.7%
        text = "안녕 Hello World"
        assert detect_language(text, threshold=0.3) == Language.ENGLISH
        assert detect_language(text, threshold=0.15) == Language.KOREAN
