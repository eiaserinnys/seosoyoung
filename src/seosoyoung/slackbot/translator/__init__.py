"""번역 모듈 패키지"""

from seosoyoung.slackbot.translator.detector import detect_language, Language
from seosoyoung.slackbot.translator.translator import translate
from seosoyoung.slackbot.translator.glossary import GlossaryMatchResult

__all__ = ["detect_language", "Language", "translate", "GlossaryMatchResult"]
