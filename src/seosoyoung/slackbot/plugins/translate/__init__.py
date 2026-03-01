"""Translate plugin package.

Re-exports from the translator modules for backward compatibility.
"""

from seosoyoung.slackbot.plugins.translate.detector import detect_language, Language
from seosoyoung.slackbot.plugins.translate.translator import translate
from seosoyoung.slackbot.plugins.translate.glossary import GlossaryMatchResult

__all__ = ["detect_language", "Language", "translate", "GlossaryMatchResult"]
