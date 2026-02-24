"""번역 모듈 패키지"""

from seosoyoung.translator.detector import detect_language, Language
from seosoyoung.translator.translator import translate
from seosoyoung.translator.glossary import GlossaryMatchResult

__all__ = ["detect_language", "Language", "translate", "GlossaryMatchResult"]
