"""번역 모듈 테스트"""

import pytest
from unittest.mock import patch, MagicMock

from seosoyoung.slackbot.translator.translator import (
    translate,
    _build_context_text,
    _build_prompt,
    _build_glossary_section,
    _calculate_cost,
    _translate_openai,
    _translate_anthropic,
)
from seosoyoung.slackbot.translator.detector import Language
from seosoyoung.slackbot.translator.glossary import GlossaryMatchResult
from seosoyoung.slackbot.plugins.translate.detector import Language as PluginLanguage
from seosoyoung.slackbot.plugins.translate.plugin import TranslatePlugin


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
        prompt, terms, match_result = _build_prompt("안녕하세요", Language.KOREAN)
        assert "English" in prompt
        assert "안녕하세요" in prompt

    def test_english_to_korean(self):
        """영어 -> 한국어 프롬프트"""
        prompt, terms, match_result = _build_prompt("Hello", Language.ENGLISH)
        assert "Korean" in prompt
        assert "Hello" in prompt

    def test_with_context(self):
        """컨텍스트 포함"""
        context = [{"user": "Alice", "text": "Previous message"}]
        prompt, terms, match_result = _build_prompt("Hello", Language.ENGLISH, context)
        assert "<previous_messages>" in prompt
        assert "[Alice]: Previous message" in prompt

    @patch("seosoyoung.slackbot.translator.translator.find_relevant_terms_v2")
    def test_with_glossary(self, mock_find_terms_v2):
        """용어집 포함"""
        mock_result = GlossaryMatchResult(
            matched_terms=[("펜릭스", "Fenrix")],
            extracted_words=["펜릭스"],
            debug_info={}
        )
        mock_find_terms_v2.return_value = mock_result
        prompt, terms, match_result = _build_prompt("펜릭스가 말했다.", Language.KOREAN)
        assert "<glossary>" in prompt
        assert "펜릭스 → Fenrix" in prompt
        assert terms == [("펜릭스", "Fenrix")]

    @patch("seosoyoung.slackbot.translator.translator.find_relevant_terms_v2")
    def test_without_glossary(self, mock_find_terms_v2):
        """관련 용어 없을 때 용어집 섹션 없음"""
        mock_result = GlossaryMatchResult(matched_terms=[], extracted_words=[], debug_info={})
        mock_find_terms_v2.return_value = mock_result
        prompt, terms, match_result = _build_prompt("Hello", Language.ENGLISH)
        assert "<glossary>" not in prompt
        assert terms == []


class TestBuildGlossarySection:
    """용어집 섹션 생성 테스트"""

    @patch("seosoyoung.slackbot.translator.translator.find_relevant_terms_v2")
    def test_builds_glossary_section(self, mock_find_terms_v2):
        """용어집 섹션 생성"""
        mock_result = GlossaryMatchResult(
            matched_terms=[("펜릭스", "Fenrix"), ("아리엘라", "Ariella")],
            extracted_words=["펜릭스", "아리엘라"],
            debug_info={}
        )
        mock_find_terms_v2.return_value = mock_result
        section, terms, match_result = _build_glossary_section("펜릭스와 아리엘라", Language.KOREAN)
        assert "<glossary>" in section
        assert "</glossary>" in section
        assert "펜릭스 → Fenrix" in section
        assert "아리엘라 → Ariella" in section
        assert terms == [("펜릭스", "Fenrix"), ("아리엘라", "Ariella")]

    @patch("seosoyoung.slackbot.translator.translator.find_relevant_terms_v2")
    def test_empty_when_no_terms(self, mock_find_terms_v2):
        """관련 용어 없으면 빈 튜플"""
        mock_result = GlossaryMatchResult(matched_terms=[], extracted_words=[], debug_info={})
        mock_find_terms_v2.return_value = mock_result
        section, terms, match_result = _build_glossary_section("Hello world", Language.ENGLISH)
        assert section == ""
        assert terms == []


class TestCalculateCost:
    """비용 계산 테스트"""

    def test_calculate_cost_basic(self):
        """기본 비용 계산 (Haiku 모델)"""
        # 1000 input tokens, 100 output tokens (Haiku 가격 기준)
        # input: 1000 / 1M * $0.80 = $0.0008
        # output: 100 / 1M * $4.00 = $0.0004
        # total: $0.0012
        cost = _calculate_cost(1000, 100, "claude-3-5-haiku-latest")
        assert abs(cost - 0.0012) < 0.0001

    def test_calculate_cost_zero(self):
        """0 토큰"""
        cost = _calculate_cost(0, 0, "claude-3-5-haiku-latest")
        assert cost == 0.0

    def test_calculate_cost_sonnet(self):
        """Sonnet 모델 비용 계산"""
        # 1000 input tokens, 100 output tokens (Sonnet 가격 기준)
        # input: 1000 / 1M * $3.00 = $0.003
        # output: 100 / 1M * $15.00 = $0.0015
        # total: $0.0045
        cost = _calculate_cost(1000, 100, "claude-sonnet-4-20250514")
        assert abs(cost - 0.0045) < 0.0001

    def test_calculate_cost_unknown_model(self):
        """알 수 없는 모델은 기본 가격 사용"""
        # 기본 가격: input $3.00, output $15.00
        cost = _calculate_cost(1000, 100, "unknown-model")
        assert abs(cost - 0.0045) < 0.0001

    def test_calculate_cost_openai_gpt5_mini(self):
        """OpenAI gpt-5-mini 비용 계산"""
        # input: 1000 / 1M * $0.40 = $0.0004
        # output: 100 / 1M * $1.60 = $0.00016
        # total: $0.00056
        cost = _calculate_cost(1000, 100, "gpt-5-mini")
        assert abs(cost - 0.00056) < 0.00001

    def test_calculate_cost_openai_gpt4_1_mini(self):
        """OpenAI gpt-4.1-mini 비용 계산"""
        cost = _calculate_cost(1000, 100, "gpt-4.1-mini")
        assert abs(cost - 0.00056) < 0.00001


class TestTranslate:
    """번역 함수 테스트"""

    @patch("seosoyoung.slackbot.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_korean_to_english(self, mock_config, mock_anthropic_class):
        """한국어 -> 영어 번역"""
        # Config mock
        mock_config.translate.api_key = "test-key"
        mock_config.translate.model = "claude-3-5-haiku-latest"

        # Anthropic client mock
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost, terms, match_result = translate("안녕하세요", Language.KOREAN)

        assert text == "Hello"
        assert cost > 0
        assert isinstance(terms, list)
        mock_client.messages.create.assert_called_once()

    @patch("seosoyoung.slackbot.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_english_to_korean(self, mock_config, mock_anthropic_class):
        """영어 -> 한국어 번역"""
        mock_config.translate.api_key = "test-key"
        mock_config.translate.model = "claude-3-5-haiku-latest"

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="안녕하세요")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost, terms, match_result = translate("Hello", Language.ENGLISH)

        assert text == "안녕하세요"
        assert cost > 0
        assert isinstance(terms, list)

    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_without_api_key(self, mock_config):
        """API 키 없이 호출 시 에러"""
        mock_config.translate.api_key = None

        with pytest.raises(ValueError, match="TRANSLATE_API_KEY"):
            translate("Hello", Language.ENGLISH)

    @patch("seosoyoung.slackbot.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_with_custom_model(self, mock_config, mock_anthropic_class):
        """커스텀 모델 사용"""
        mock_config.translate.api_key = "test-key"
        mock_config.translate.model = "default-model"

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

    @patch("seosoyoung.slackbot.translator.translator.find_relevant_terms_v2")
    @patch("seosoyoung.slackbot.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_returns_glossary_terms(self, mock_config, mock_anthropic_class, mock_find_terms_v2):
        """번역 시 참고한 용어 목록 반환"""
        mock_config.translate.api_key = "test-key"
        mock_config.translate.model = "claude-3-5-haiku-latest"

        mock_result = GlossaryMatchResult(
            matched_terms=[("펜릭스", "Fenrix"), ("아리엘라", "Ariella")],
            extracted_words=["펜릭스", "아리엘라"],
            debug_info={}
        )
        mock_find_terms_v2.return_value = mock_result

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Fenrix and Ariella")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost, terms, match_result = translate("펜릭스와 아리엘라", Language.KOREAN)

        assert text == "Fenrix and Ariella"
        assert terms == [("펜릭스", "Fenrix"), ("아리엘라", "Ariella")]


class TestTranslateOpenAI:
    """OpenAI 번역 테스트"""

    @patch("seosoyoung.slackbot.translator.translator.openai.OpenAI")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_openai_korean_to_english(self, mock_config, mock_openai_class):
        """OpenAI backend로 한국어 -> 영어 번역"""
        mock_config.translate.backend = "openai"
        mock_config.om.openai_api_key = "test-openai-key"
        mock_config.translate.openai_model = "gpt-5-mini"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        text, cost, terms, match_result = translate("안녕하세요", Language.KOREAN, backend="openai")

        assert text == "Hello"
        assert cost > 0
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-5-mini"

    @patch("seosoyoung.slackbot.translator.translator.openai.OpenAI")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_openai_without_api_key(self, mock_config, mock_openai_class):
        """OpenAI API 키 없이 호출 시 에러"""
        mock_config.translate.backend = "openai"
        mock_config.om.openai_api_key = None

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            translate("Hello", Language.ENGLISH, backend="openai")

    @patch("seosoyoung.slackbot.translator.translator.openai.OpenAI")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_openai_default_backend(self, mock_config, mock_openai_class):
        """Config.TRANSLATE_BACKEND=openai일 때 자동으로 OpenAI 사용"""
        mock_config.translate.backend = "openai"
        mock_config.om.openai_api_key = "test-openai-key"
        mock_config.translate.openai_model = "gpt-5-mini"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_response

        text, cost, terms, match_result = translate("안녕하세요", Language.KOREAN)

        assert text == "Hello"
        mock_client.chat.completions.create.assert_called_once()

    @patch("seosoyoung.slackbot.translator.translator.anthropic.Anthropic")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_backend_switch_to_anthropic(self, mock_config, mock_anthropic_class):
        """backend 파라미터로 anthropic 명시적 지정"""
        mock_config.translate.backend = "openai"  # 기본은 openai지만
        mock_config.translate.api_key = "test-anthropic-key"
        mock_config.translate.model = "claude-3-5-haiku-latest"

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="안녕하세요")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response

        text, cost, terms, match_result = translate(
            "Hello", Language.ENGLISH, backend="anthropic"
        )

        assert text == "안녕하세요"
        mock_client.messages.create.assert_called_once()

    @patch("seosoyoung.slackbot.translator.translator.openai.OpenAI")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_openai_uses_max_completion_tokens(self, mock_config, mock_openai_class):
        """OpenAI API 호출 시 max_completion_tokens 사용 (max_tokens 아님)"""
        mock_config.translate.backend = "openai"
        mock_config.om.openai_api_key = "test-key"
        mock_config.translate.openai_model = "gpt-5-mini"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        translate("안녕하세요", Language.KOREAN, backend="openai")

        call_args = mock_client.chat.completions.create.call_args
        assert "max_completion_tokens" in call_args.kwargs
        assert "max_tokens" not in call_args.kwargs
        assert call_args.kwargs["max_completion_tokens"] == 2048

    @patch("seosoyoung.slackbot.translator.translator.openai.OpenAI")
    @patch("seosoyoung.slackbot.translator.translator.Config")
    def test_translate_openai_custom_model(self, mock_config, mock_openai_class):
        """OpenAI에서 커스텀 모델 사용"""
        mock_config.translate.backend = "openai"
        mock_config.om.openai_api_key = "test-key"
        mock_config.translate.openai_model = "gpt-5-mini"

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Result"))]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response

        translate("Test", Language.ENGLISH, model="gpt-4o", backend="openai")

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4o"


class TestFormatResponse:
    """응답 포맷팅 테스트 (TranslatePlugin._format_response)"""

    @pytest.fixture(autouse=True)
    def _setup_plugin(self):
        """테스트 전 기본 show_glossary=False, show_cost=True 플러그인 설정"""
        self.plugin = TranslatePlugin()
        # on_load 없이 필요한 필드만 직접 설정 (테스트 전용)
        self.plugin._show_glossary = False
        self.plugin._show_cost = True

    def test_korean_to_english_without_glossary(self):
        """한국어 -> 영어 (용어집 없음)"""
        result = self.plugin._format_response("홍길동", "Hello", PluginLanguage.KOREAN, 0.0012)
        assert "`홍길동 said,`" in result
        assert '"Hello"' in result
        assert "`~💵$0.0012`" in result
        assert "📖" not in result

    def test_english_to_korean_without_glossary(self):
        """영어 -> 한국어 (용어집 없음)"""
        result = self.plugin._format_response("John", "안녕하세요", PluginLanguage.ENGLISH, 0.0012)
        assert "`John님이`" in result
        assert '"안녕하세요"' in result
        assert "`라고 하셨습니다.`" in result
        assert "`~💵$0.0012`" in result
        assert "📖" not in result

    def test_korean_to_english_with_glossary(self):
        """한국어 -> 영어 (용어집 있음, 표시 켜짐)"""
        self.plugin._show_glossary = True
        terms = [("펜릭스", "Fenrix"), ("아리엘라", "Ariella")]
        result = self.plugin._format_response("홍길동", "Fenrix and Ariella", PluginLanguage.KOREAN, 0.0012, terms)
        assert "`홍길동 said,`" in result
        assert "`📖 펜릭스 (Fenrix), 아리엘라 (Ariella)`" in result
        assert "`~💵$0.0012`" in result

    def test_english_to_korean_with_glossary(self):
        """영어 -> 한국어 (용어집 있음, 표시 켜짐)"""
        self.plugin._show_glossary = True
        terms = [("Fenrix", "펜릭스")]
        result = self.plugin._format_response("John", "펜릭스가 말했다", PluginLanguage.ENGLISH, 0.0012, terms)
        assert "`John님이`" in result
        assert "`📖 Fenrix (펜릭스)`" in result
        assert "`~💵$0.0012`" in result

    def test_with_empty_glossary(self):
        """빈 용어집"""
        self.plugin._show_glossary = True
        result = self.plugin._format_response("홍길동", "Hello", PluginLanguage.KOREAN, 0.0012, [])
        assert "📖" not in result

    def test_with_none_glossary(self):
        """None 용어집"""
        self.plugin._show_glossary = True
        result = self.plugin._format_response("홍길동", "Hello", PluginLanguage.KOREAN, 0.0012, None)
        assert "📖" not in result

    def test_glossary_hidden_when_option_off(self):
        """용어집 표시 옵션 꺼짐"""
        self.plugin._show_glossary = False
        terms = [("펜릭스", "Fenrix")]
        result = self.plugin._format_response("홍길동", "Fenrix", PluginLanguage.KOREAN, 0.0012, terms)
        assert "📖" not in result

    def test_cost_hidden_when_option_off(self):
        """비용 표시 옵션 꺼짐"""
        self.plugin._show_glossary = False
        self.plugin._show_cost = False
        result = self.plugin._format_response("홍길동", "Hello", PluginLanguage.KOREAN, 0.0012)
        assert "💵" not in result
