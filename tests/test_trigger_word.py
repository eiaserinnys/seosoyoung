"""트리거 워드 감지 테스트"""

from unittest.mock import patch, MagicMock

import pytest

from seosoyoung.handlers.message import _contains_trigger_word


class TestContainsTriggerWord:
    """_contains_trigger_word 함수 테스트"""

    def test_no_trigger_words_configured(self):
        """트리거 워드가 설정되지 않으면 항상 False"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = []
            assert _contains_trigger_word("소영아 안녕") is False

    def test_match_exact(self):
        """정확히 일치하는 트리거 워드 감지"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["소영"]
            assert _contains_trigger_word("소영") is True

    def test_match_substring(self):
        """문장 내에 포함된 트리거 워드 감지"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["소영"]
            assert _contains_trigger_word("소영아 이것 좀 봐줘") is True

    def test_no_match(self):
        """트리거 워드가 없는 텍스트"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["소영"]
            assert _contains_trigger_word("오늘 날씨가 좋다") is False

    def test_case_insensitive(self):
        """대소문자 무시 매칭"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["SeoSoyoung"]
            assert _contains_trigger_word("seosoyoung is here") is True

    def test_multiple_trigger_words(self):
        """여러 트리거 워드 중 하나라도 매칭"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["소영", "서소영", "soyoung"]
            assert _contains_trigger_word("서소영 봇") is True
            assert _contains_trigger_word("안녕 소영") is True
            assert _contains_trigger_word("hey soyoung") is True
            assert _contains_trigger_word("아무 관련 없는 말") is False

    def test_empty_text(self):
        """빈 텍스트"""
        with patch("seosoyoung.handlers.message.Config") as mock_config:
            mock_config.CHANNEL_OBSERVER_TRIGGER_WORDS = ["소영"]
            assert _contains_trigger_word("") is False


class TestMaybeTriggerDigestForce:
    """_maybe_trigger_digest의 force 파라미터 테스트"""

    def test_force_bypasses_threshold(self):
        """force=True이면 임계치 미만이어도 파이프라인 트리거"""
        from seosoyoung.handlers.message import _maybe_trigger_digest

        store = MagicMock()
        observer = MagicMock()
        cooldown = MagicMock()
        compressor = MagicMock()
        client = MagicMock()

        store.count_pending_tokens.return_value = 10  # threshold_A(150)보다 작음

        with patch("seosoyoung.handlers.message.Config") as mock_config, \
             patch("seosoyoung.handlers.message._digest_running", {}), \
             patch("seosoyoung.handlers.message.threading") as mock_threading:
            mock_config.CHANNEL_OBSERVER_THRESHOLD_A = 150
            mock_config.CHANNEL_OBSERVER_THRESHOLD_B = 5000
            mock_config.CHANNEL_OBSERVER_DIGEST_MAX_TOKENS = 10000
            mock_config.CHANNEL_OBSERVER_DIGEST_TARGET_TOKENS = 5000
            mock_config.CHANNEL_OBSERVER_DEBUG_CHANNEL = ""
            mock_config.CHANNEL_OBSERVER_MAX_INTERVENTION_TURNS = 15

            _maybe_trigger_digest(
                "C001", client, store, observer, compressor, cooldown,
                force=True,
            )

            # 스레드가 시작되어야 함
            mock_threading.Thread.assert_called_once()
            mock_threading.Thread.return_value.start.assert_called_once()

    def test_no_force_respects_threshold(self):
        """force=False이면 threshold_A 미만일 때 파이프라인 실행 안 함"""
        from seosoyoung.handlers.message import _maybe_trigger_digest

        store = MagicMock()
        observer = MagicMock()
        cooldown = MagicMock()
        compressor = MagicMock()
        client = MagicMock()

        store.count_pending_tokens.return_value = 10

        with patch("seosoyoung.handlers.message.Config") as mock_config, \
             patch("seosoyoung.handlers.message._digest_running", {}), \
             patch("seosoyoung.handlers.message.threading") as mock_threading:
            mock_config.CHANNEL_OBSERVER_THRESHOLD_A = 150

            _maybe_trigger_digest(
                "C001", client, store, observer, compressor, cooldown,
                force=False,
            )

            mock_threading.Thread.assert_not_called()
