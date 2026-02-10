"""Reflector 모듈

관찰 로그가 임계치를 초과할 때 재구조화하고 압축합니다.
OpenAI API를 사용하여 관찰 로그를 요약하고, XML 태그 형식으로 결과를 파싱합니다.
"""

import logging
import re
from dataclasses import dataclass

import openai

from seosoyoung.memory.prompts import (
    build_reflector_system_prompt,
    build_reflector_retry_prompt,
)
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class ReflectorResult:
    """Reflector 출력 결과"""

    observations: str
    token_count: int


def _extract_observations(text: str) -> str:
    """응답에서 <observations> 태그 내용을 추출합니다. 없으면 전체 텍스트."""
    match = re.search(r"<observations>(.*?)</observations>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


class Reflector:
    """관찰 로그를 압축하고 재구조화"""

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.token_counter = TokenCounter()

    async def reflect(
        self,
        observations: str,
        target_tokens: int = 15000,
    ) -> ReflectorResult | None:
        """관찰 로그를 압축합니다.

        Args:
            observations: 압축할 관찰 로그
            target_tokens: 목표 토큰 수

        Returns:
            ReflectorResult 또는 None (API 오류 시)
        """
        system_prompt = build_reflector_system_prompt()

        try:
            # 1차 시도
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": observations},
                ],
                temperature=0.3,
                max_tokens=16_000,
            )

            result_text = response.choices[0].message.content or ""
            compressed = _extract_observations(result_text)
            token_count = self.token_counter.count_string(compressed)

            logger.info(f"Reflector 1차 압축: {token_count} tokens (목표: {target_tokens})")

            # 목표 이하면 바로 반환
            if token_count <= target_tokens:
                return ReflectorResult(
                    observations=compressed,
                    token_count=token_count,
                )

            # 2차 시도 (재시도)
            retry_prompt = build_reflector_retry_prompt(token_count, target_tokens)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": observations},
                    {"role": "assistant", "content": result_text},
                    {"role": "user", "content": retry_prompt},
                ],
                temperature=0.3,
                max_tokens=16_000,
            )

            retry_text = response.choices[0].message.content or ""
            compressed = _extract_observations(retry_text)
            token_count = self.token_counter.count_string(compressed)

            logger.info(f"Reflector 2차 압축: {token_count} tokens (목표: {target_tokens})")

            return ReflectorResult(
                observations=compressed,
                token_count=token_count,
            )

        except Exception as e:
            logger.error(f"Reflector API 호출 실패: {e}")
            return None
