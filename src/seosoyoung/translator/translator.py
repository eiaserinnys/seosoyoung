"""번역 모듈

Anthropic API를 직접 호출하여 번역합니다.
"""

import logging
import anthropic

from seosoyoung.config import Config
from seosoyoung.translator.detector import Language

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

    context_text = ""
    if context_messages:
        context_text = _build_context_text(context_messages) + "\n\n"

    return f"""{context_text}Translate the following text to {target_lang}.
Output ONLY the translation, nothing else. No explanations, no quotes, no prefixes.

Text to translate:
{text}"""


# Claude Haiku 4 가격 (2025년 기준, USD per 1M tokens)
HAIKU_INPUT_PRICE = 0.80   # $0.80 / 1M input tokens
HAIKU_OUTPUT_PRICE = 4.00  # $4.00 / 1M output tokens


def _calculate_cost(input_tokens: int, output_tokens: int) -> float:
    """토큰 사용량으로 비용을 계산합니다.

    Args:
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수

    Returns:
        예상 비용 (USD)
    """
    input_cost = (input_tokens / 1_000_000) * HAIKU_INPUT_PRICE
    output_cost = (output_tokens / 1_000_000) * HAIKU_OUTPUT_PRICE
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
    cost = _calculate_cost(input_tokens, output_tokens)

    logger.debug(f"번역 완료: {translated[:50]}... (비용: ${cost:.6f})")

    return translated, cost
