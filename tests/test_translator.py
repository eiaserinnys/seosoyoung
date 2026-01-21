"""번역 모듈 테스트"""

import pytest
from unittest.mock import patch, MagicMock

from seosoyoung.translator.translator import (
    translate,
    _build_context_text,
    _build_prompt,
    _build_glossary_section,
    _calculate_cost,
)
from seosoyoung.translator.detector import Language


class TestBuildContextText:
    """컨텍스트 텍스트 생성 테스트"""

    def test_empty_context(self):
        """빈 컨텍스트"""
        assert _build_context_text([]) == ""

    def test_single_message(self):
        """단일 메시지"""
        context = [{"user": "Alice", "text": "Hello"}]
        result = _build_context_text(context)
        assert "<previous_messages>" in result
        assert "[Alice]: Hello" in result
        assert "</previous_messages>" in result

    def test_multiple_messages(self):
        """여러 메시지"""
        context = [
            {"user": "Alice", "text": "Hello"},
            {"user": "Bob", "text": "Hi there"},
        ]
        result = _build_context_text(context)
        assert "[Alice]: Hello" in result
        assert "[Bob]: Hi there" in result


class TestBuildPrompt:
    """프롬프트 생성 테스트"""

    def test_korean_to_english(self):
        """한국어 -> 영어 프롬프트"""
        prompt = _build_prompt("안녕하세요", Language.KOREAN)
        assert "English" in prompt
        assert "안녕하세요" in prompt

    def test_english_to_korean(self):
        """영어 -> 한국어 프롬프트"""
        prompt = _build_prompt("Hello", Language.ENGLISH)
        assert "Korean" in prompt
        assert "Hello" in prompt

    def test_with_context(self):
        """컨텍스트 포함"""
        context = [{"user": "Alice", "text": "Previous message"}]
        prompt = _build_prompt("Hello", Language.ENGLISH, context)
        assert "<previous_messages>" in prompt
        assert "[Alice]: Previous message" in prompt

    @patch("seosoyoung.translator.translator.find_relevant_terms")
    def test_with_glossary(self, mock_find_terms):
        """용어집 포함"""
        mock_find_terms.return_value = [("펜릭스", "Fenrix")]
        prompt = _build_prompt("펜릭스가 말했다.", Language.KOREAN)
        assert "<glossary>" in prompt
        assert "펜릭스 → Fenrix" in prompt

    @patch("seosoyoung.translator.translator.find_relevant_terms")
    def test_without_glossary(self, mock_find_terms):
        """관련 용어 없을 때 용어집 섹션 없음"""
        mock_find_terms.return_value = []
        prompt = _build_prompt("Hello", Language.ENGLISH)
        assert "<glossary>" not in prompt


class TestBuildGlossarySection:
    """용어집 섹션 생성 테스트"""

    @patch("seosoyoung.translator.translator.find_relevant_terms")
    def test_builds_glossary_section(self, mock_find_terms):
        """용어집 섹션 생성"""
        mock_find_terms.return_value = [
            ("펜릭스", "Fenrix"),
            ("아리엘라", "Ariella"),
        ]
        section = _build_glossary_section("펜릭스와 아리엘라", Language.KOREAN)
        assert "<glossary>" in section
        assert "</glossary>" in section
        assert "펜릭스 → Fenrix" in section
        assert "아리엘라 → Ariella" in section

    @patch("seosoyoung.translator.translator.find_relevant_terms")
    def test_empty_when_no_terms(self, mock_find_terms):
        """관련 용어 없으면 빈 문자열"""
        mock_find_terms.return_value = []
        section = _build_glossary_section("Hello world", Language.ENGLISH)
        assert section == ""


class TestCalculateCost:
    """비용 계산 테스트"""

    def test_calculate_cost_basic(self):
        """기본 비용 계산"""
        # 1000 input tokens, 100 output tokens
        # input: 1000 / 1M * $0.80 = $0.0008
        # output: 100 / 1M * $4.00 = $0.0004
        # total: $0.0012
        cost = _calculate_cost(1000, 100)
        assert abs(cost - 0.0012) < 0.0001

    def test_calculate_cost_zero(self):
        """0 토큰"""
        cost = _calculate_cost(0, 0)
        assert cost == 0.0


class TestTranslate:
    """번역 함수 테스트"""

    @patch("seosoyoung.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.translator.translator.Config")
    def test_translate_korean_to_english(self, mock_config, mock_anthropic_class):
        """한국어 -> 영어 번역"""
        # Config mock
        mock_config.TRANSLATE_API_KEY = "test-key"
        mock_config.TRANSLATE_MODEL = "claude-3-5-haiku-latest"

        # Anthropic client mock
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost = translate("안녕하세요", Language.KOREAN)

        assert text == "Hello"
        assert cost > 0
        mock_client.messages.create.assert_called_once()

    @patch("seosoyoung.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.translator.translator.Config")
    def test_translate_english_to_korean(self, mock_config, mock_anthropic_class):
        """영어 -> 한국어 번역"""
        mock_config.TRANSLATE_API_KEY = "test-key"
        mock_config.TRANSLATE_MODEL = "claude-3-5-haiku-latest"

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="안녕하세요")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost = translate("Hello", Language.ENGLISH)

        assert text == "안녕하세요"
        assert cost > 0

    @patch("seosoyoung.translator.translator.Config")
    def test_translate_without_api_key(self, mock_config):
        """API 키 없이 호출 시 에러"""
        mock_config.TRANSLATE_API_KEY = None

        with pytest.raises(ValueError, match="TRANSLATE_API_KEY"):
            translate("Hello", Language.ENGLISH)

    @patch("seosoyoung.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.translator.translator.Config")
    def test_translate_with_custom_model(self, mock_config, mock_anthropic_class):
        """커스텀 모델 사용"""
        mock_config.TRANSLATE_API_KEY = "test-key"
        mock_config.TRANSLATE_MODEL = "default-model"

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Result")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        translate("Test", Language.ENGLISH, model="custom-model")

        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "custom-model"
