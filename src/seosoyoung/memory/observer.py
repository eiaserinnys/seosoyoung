"""Observer 모듈

대화 내용을 분석하여 구조화된 관찰 로그를 생성합니다.
OpenAI API를 사용하여 대화를 관찰하고, XML 태그 형식으로 결과를 파싱합니다.
"""

import logging
import re
from dataclasses import dataclass

import openai

from seosoyoung.memory.prompts import (
    build_observer_system_prompt,
    build_observer_user_prompt,
)
from seosoyoung.memory.token_counter import TokenCounter

logger = logging.getLogger(__name__)


@dataclass
class ObserverResult:
    """Observer 출력 결과"""

    observations: str = ""
    current_task: str = ""
    suggested_response: str = ""


def parse_observer_output(text: str) -> ObserverResult:
    """Observer 응답에서 XML 태그를 파싱합니다.

    <observations>, <current-task>, <suggested-response> 태그를 추출합니다.
    태그가 없는 경우 전체 응답을 observations로 사용합니다 (fallback).
    """
    observations = _extract_tag(text, "observations")
    current_task = _extract_tag(text, "current-task")
    suggested_response = _extract_tag(text, "suggested-response")

    # fallback: observations 태그가 없으면 전체 응답을 사용
    if not observations:
        observations = text.strip()

    return ObserverResult(
        observations=observations,
        current_task=current_task,
        suggested_response=suggested_response,
    )


def _extract_tag(text: str, tag_name: str) -> str:
    """XML 태그 내용을 추출합니다. 없으면 빈 문자열."""
    pattern = rf"<{tag_name}>(.*?)</{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


class Observer:
    """대화를 관찰하여 구조화된 관찰 로그를 생성"""

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.token_counter = TokenCounter()

    async def observe(
        self,
        existing_observations: str | None,
        messages: list[dict],
        min_conversation_tokens: int = 500,
    ) -> ObserverResult | None:
        """대화를 관찰하여 새 관찰 로그를 생성합니다.

        Args:
            existing_observations: 기존 관찰 로그 (없으면 None)
            messages: 세션 대화 내역
            min_conversation_tokens: 최소 대화 토큰 수 (미달 시 None 반환)

        Returns:
            ObserverResult 또는 None (대화가 너무 짧은 경우)
        """
        # 최소 대화 길이 체크
        conversation_tokens = self.token_counter.count_messages(messages)
        if conversation_tokens < min_conversation_tokens:
            logger.info(
                f"대화가 너무 짧아 관찰을 건너뜁니다 "
                f"({conversation_tokens} < {min_conversation_tokens} tokens)"
            )
            return None

        system_prompt = build_observer_system_prompt()
        user_prompt = build_observer_user_prompt(existing_observations, messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=16_000,
        )

        result_text = response.choices[0].message.content or ""
        return parse_observer_output(result_text)
