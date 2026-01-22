"""번역 모듈

Anthropic API를 직접 호출하여 번역합니다.
"""

import logging
import anthropic

from seosoyoung.config import Config
from seosoyoung.translator.detector import Language
from seosoyoung.translator.glossary import find_relevant_terms

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


def _build_glossary_section(text: str, source_lang: Language) -> str:
    """텍스트에서 관련 용어를 찾아 용어집 섹션 생성

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어

    Returns:
        용어집 섹션 문자열 (관련 용어가 없으면 빈 문자열)
    """
    lang_code = "ko" if source_lang == Language.KOREAN else "en"
    relevant_terms = find_relevant_terms(text, lang_code)

    if not relevant_terms:
        return ""

    lines = ["<glossary>", "Translate the following proper nouns as specified:"]
    for source_term, target_term in relevant_terms:
        lines.append(f"- {source_term} → {target_term}")
    lines.append("</glossary>")

    return "\n".join(lines)


def _build_prompt(
    text: str,
    source_lang: Language,
    context_messages: list[dict] | None = None
) -> str:
    """번역 프롬프트 생성

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어
        context_messages: 이전 대화 컨텍스트

    Returns:
        프롬프트 문자열
    """
    target_lang = "English" if source_lang == Language.KOREAN else "Korean"

    # 컨텍스트 섹션
    context_text = ""
    if context_messages:
        context_text = _build_context_text(context_messages) + "\n\n"

    # 용어집 섹션
    glossary_section = _build_glossary_section(text, source_lang)
    glossary_text = glossary_section + "\n\n" if glossary_section else ""

    return f"""{context_text}{glossary_text}Translate the following text to {target_lang}.
Output ONLY the translation, nothing else. No explanations, no quotes, no prefixes.

Text to translate:
{text}"""


# 모델별 가격 (2025년 기준, USD per 1M tokens)
MODEL_PRICING = {
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-latest": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
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


def translate(
    text: str,
    source_lang: Language,
    context_messages: list[dict] | None = None,
    model: str | None = None,
) -> tuple[str, float]:
    """텍스트를 번역

    Args:
        text: 번역할 텍스트
        source_lang: 원본 언어
        context_messages: 이전 대화 컨텍스트
        model: 사용할 모델 (기본값: Config.TRANSLATE_MODEL)

    Returns:
        (번역된 텍스트, 예상 비용 USD)

    Raises:
        Exception: API 호출 실패 시
    """
    api_key = Config.TRANSLATE_API_KEY
    if not api_key:
        raise ValueError("TRANSLATE_API_KEY가 설정되지 않았습니다.")

    model = model or Config.TRANSLATE_MODEL
    prompt = _build_prompt(text, source_lang, context_messages)

    logger.debug(f"번역 요청: {text[:50]}... -> {source_lang.value}")

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    translated = response.content[0].text.strip()

    # 토큰 사용량에서 비용 계산
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = _calculate_cost(input_tokens, output_tokens, model)

    logger.debug(f"번역 완료: {translated[:50]}... (비용: ${cost:.6f})")

    return translated, cost
