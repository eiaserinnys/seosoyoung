"""번역 모듈

Anthropic 또는 OpenAI API를 호출하여 번역합니다.
backend 설정(Config.translate.backend)에 따라 분기합니다.
"""

import logging
import anthropic
import openai

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.translator.detector import Language
from seosoyoung.slackbot.translator.glossary import find_relevant_terms_v2, GlossaryMatchResult

logger = logging.getLogger(__name__)


def _build_context_text(context_messages: list[dict]) -> str:
    """이전 대화 컨텍스트를 텍스트로 변환

    Args:
        context_messages: 이전 메시지 목록 [{"user": "이름", "text": "내용"}, ...]

    Returns:
        컨텍스트 텍스트
    """
    if not context_messages:
        return ""

    lines = ["<previous_messages>"]
    for msg in context_messages:
        lines.append(f"[{msg['user']}]: {msg['text']}")
    lines.append("</previous_messages>")
    return "\n".join(lines)


def _build_glossary_section(text: str, source_lang: Language) -> tuple[str, list[tuple[str, str]], GlossaryMatchResult | None]:
    """텍스트에서 관련 용어를 찾아 용어집 섹션 생성

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어

    Returns:
        (용어집 섹션 문자열, 참고한 용어 목록, 매칭 결과 객체)
        용어가 없으면 ("", [], None)
    """
    lang_code = "ko" if source_lang == Language.KOREAN else "en"
    match_result = find_relevant_terms_v2(text, lang_code)

    if not match_result.matched_terms:
        return "", [], match_result

    lines = ["<glossary>", "Translate the following proper nouns as specified:"]
    for source_term, target_term in match_result.matched_terms:
        lines.append(f"- {source_term} → {target_term}")
    lines.append("</glossary>")

    return "\n".join(lines), match_result.matched_terms, match_result


def _build_prompt(
    text: str,
    source_lang: Language,
    context_messages: list[dict] | None = None
) -> tuple[str, list[tuple[str, str]], GlossaryMatchResult | None]:
    """번역 프롬프트 생성

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어
        context_messages: 이전 대화 컨텍스트

    Returns:
        (프롬프트 문자열, 참고한 용어 목록, 매칭 결과 객체)
    """
    target_lang = "English" if source_lang == Language.KOREAN else "Korean"

    # 컨텍스트 섹션
    context_text = ""
    if context_messages:
        context_text = _build_context_text(context_messages) + "\n\n"

    # 용어집 섹션
    glossary_section, glossary_terms, match_result = _build_glossary_section(text, source_lang)
    glossary_text = glossary_section + "\n\n" if glossary_section else ""

    prompt = f"""{context_text}{glossary_text}Translate the following text to {target_lang}.
Output ONLY the translation, nothing else. No explanations, no quotes, no prefixes.

Text to translate:
{text}"""
    return prompt, glossary_terms, match_result


# 모델별 가격 (USD per 1M tokens)
MODEL_PRICING = {
    # Anthropic
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    # OpenAI
    "gpt-5-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

# 기본 가격 (알 수 없는 모델용)
DEFAULT_PRICING = {"input": 3.00, "output": 15.00}


def _calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """토큰 사용량으로 비용을 계산합니다.

    Args:
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
        model: 사용한 모델명

    Returns:
        예상 비용 (USD)
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def _translate_anthropic(prompt: str, model: str, api_key: str) -> tuple[str, int, int]:
    """Anthropic API로 번역

    Returns:
        (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)
    """
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    translated = response.content[0].text.strip()
    return translated, response.usage.input_tokens, response.usage.output_tokens


def _translate_openai(prompt: str, model: str, api_key: str) -> tuple[str, int, int]:
    """OpenAI API로 번역

    Returns:
        (번역된 텍스트, 입력 토큰 수, 출력 토큰 수)
    """
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=2048,
    )
    translated = response.choices[0].message.content.strip()
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    return translated, input_tokens, output_tokens


def translate(
    text: str,
    source_lang: Language,
    context_messages: list[dict] | None = None,
    model: str | None = None,
    backend: str | None = None,
) -> tuple[str, float, list[tuple[str, str]], GlossaryMatchResult | None]:
    """텍스트를 번역

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어
        context_messages: 이전 대화 컨텍스트
        model: 사용할 모델 (기본값: backend에 따라 Config에서 결정)
        backend: 번역 백엔드 ("anthropic" | "openai", 기본값: Config.translate.backend)

    Returns:
        (번역된 텍스트, 예상 비용 USD, 참고한 용어 목록, 매칭 결과 객체)

    Raises:
        ValueError: API 키 미설정 또는 잘못된 backend
    """
    backend = backend or Config.translate.backend

    if backend == "openai":
        api_key = Config.om.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        model = model or Config.translate.openai_model
    else:
        api_key = Config.translate.api_key
        if not api_key:
            raise ValueError("TRANSLATE_API_KEY가 설정되지 않았습니다.")
        model = model or Config.translate.model

    prompt, glossary_terms, match_result = _build_prompt(text, source_lang, context_messages)

    logger.debug(f"번역 요청 [{backend}]: {text[:50]}... -> {source_lang.value}")

    if backend == "openai":
        translated, input_tokens, output_tokens = _translate_openai(prompt, model, api_key)
    else:
        translated, input_tokens, output_tokens = _translate_anthropic(prompt, model, api_key)

    cost = _calculate_cost(input_tokens, output_tokens, model)

    logger.debug(f"번역 완료 [{backend}]: {translated[:50]}... (비용: ${cost:.6f})")

    return translated, cost, glossary_terms, match_result
