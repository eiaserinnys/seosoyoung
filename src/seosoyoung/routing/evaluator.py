"""하이쿠 평가 클라이언트

Anthropic SDK로 하이쿠 모델을 호출하여 도구 적합도를 평가하는 모듈.
"""

from dataclasses import dataclass
from typing import Any
import asyncio
import json
import logging
import re

from .loader import ToolDefinition


logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_MODEL = "claude-3-5-haiku-latest"
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 0.5
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_SUITABILITY_THRESHOLD = 5


def build_evaluation_prompt(tool: ToolDefinition, user_request: str) -> str:
    """도구 평가를 위한 프롬프트 생성.

    Args:
        tool: 평가할 도구 정의
        user_request: 사용자 요청

    Returns:
        평가 프롬프트 문자열
    """
    tool_type = tool.tool_type
    tool_name = tool.name
    tool_description = tool.description
    tool_body = tool.body

    return f"""당신은 AI 도구 라우팅 전문가입니다. 사용자의 요청이 주어진 도구에 얼마나 적합한지 평가해주세요.

## 도구 정보
- **이름**: {tool_name}
- **유형**: {tool_type}
- **요약**: {tool_description}

## 도구 문서 전체 내용
{tool_body}

## 사용자 요청
"{user_request}"

## 평가 절차
1. 도구 문서의 각 부분을 읽으면서 사용자 요청과의 연관도를 평가하세요
2. 요청에 **직접적이고 구체적인** 정보를 제공하는 부분에 높은 점수를 부여하세요
3. 가장 연관도가 높은 상위 3개 부분을 선정하세요
4. 선정된 부분들을 바탕으로 전체 적합도 점수(1-10)를 매기세요

## 적합도 점수 기준
- 9-10점: 이 도구가 요청을 처리하기에 완벽하게 적합
- 7-8점: 높은 적합도, 도구가 요청을 잘 처리할 수 있음
- 5-6점: 중간 적합도, 도구가 부분적으로 도움이 될 수 있음
- 3-4점: 낮은 적합도, 도구가 요청과 약간만 관련됨
- 1-2점: 매우 낮은 적합도, 도구가 요청과 거의 무관함

## 응답 형식
반드시 다음 JSON 형식으로만 응답하세요:
```json
{{
    "score": <1-10 사이의 정수>,
    "relevant_excerpts": [
        "<문서에서 발췌한 첫 번째로 연관도 높은 부분>",
        "<문서에서 발췌한 두 번째로 연관도 높은 부분>",
        "<문서에서 발췌한 세 번째로 연관도 높은 부분>"
    ],
    "approach": "<이 도구로 요청을 처리한다면 어떤 접근 방식을 취할지 간략히 설명>"
}}
```

**중요**:
- `relevant_excerpts`는 반드시 문서 본문에서 **그대로 복사**해야 합니다
- 각 발췌 부분은 1-3줄 정도의 짧은 텍스트로 제한하세요
- 자신의 판단이나 해석을 추가하지 말고, 원문 그대로 인용하세요
- 관련 부분이 3개 미만이면 빈 문자열로 채우세요"""


def parse_evaluation_response(
    response: str, tool_name: str, tool_type: str = "unknown"
) -> "EvaluationResult":
    """평가 응답 파싱.

    Args:
        response: 모델 응답 텍스트
        tool_name: 도구 이름
        tool_type: 도구 타입 (agent, skill, unknown)

    Returns:
        EvaluationResult 객체
    """
    # 마크다운 코드 펜스 제거
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
    if json_match:
        response = json_match.group(1)

    try:
        data = json.loads(response.strip())
        score = data.get("score", 0)
        relevant_excerpts = data.get("relevant_excerpts", [])
        approach = data.get("approach", "접근 방식 미정")

        # 점수 클램핑
        score = max(0, min(10, int(score)))

        # 발췌 부분을 개행으로 연결
        excerpts_text = "\n\n".join(
            f"• {excerpt}" for excerpt in relevant_excerpts if excerpt
        )

        return EvaluationResult(
            tool_name=tool_name,
            score=score,
            reason=excerpts_text,
            approach=approach,
            tool_type=tool_type,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning(f"JSON 파싱 실패, 정규식 폴백 시도: {e}")
        return _parse_with_regex_fallback(response, tool_name, tool_type)


def _parse_with_regex_fallback(
    response: str, tool_name: str, tool_type: str = "unknown"
) -> "EvaluationResult":
    """정규식을 사용한 폴백 파싱.

    Args:
        response: 모델 응답 텍스트
        tool_name: 도구 이름
        tool_type: 도구 타입 (agent, skill, unknown)

    Returns:
        EvaluationResult 객체
    """
    # 점수 추출 시도
    score_match = re.search(r"(?:score|점수)[:\s]*(\d+)", response, re.IGNORECASE)
    score = int(score_match.group(1)) if score_match else 0
    score = max(0, min(10, score))

    # relevant_excerpts 배열 추출 시도
    excerpts_match = re.search(
        r"(?:relevant_excerpts|관련[_\s]?발췌)[:\s]*\[(.*?)\]",
        response,
        re.IGNORECASE | re.DOTALL
    )
    if excerpts_match:
        # 간단한 파싱: 따옴표로 감싼 부분들을 추출
        excerpts_text = excerpts_match.group(1)
        excerpts = re.findall(r'"([^"]+)"', excerpts_text)
        excerpts_formatted = "\n\n".join(f"• {e}" for e in excerpts if e)
    else:
        excerpts_formatted = ""

    # 접근 방식 추출 시도
    approach_match = re.search(
        r"(?:approach|접근)[:\s]*([^\n]+)", response, re.IGNORECASE
    )
    approach = approach_match.group(1).strip() if approach_match else "파싱 실패"

    return EvaluationResult(
        tool_name=tool_name,
        score=score,
        reason=excerpts_formatted,
        approach=approach,
        tool_type=tool_type,
    )


@dataclass
class EvaluationResult:
    """도구 평가 결과"""

    tool_name: str
    score: int
    reason: str
    approach: str
    tool_type: str = "unknown"  # agent, skill, unknown
    threshold: int = DEFAULT_SUITABILITY_THRESHOLD

    @property
    def is_suitable(self) -> bool:
        """임계값 이상이면 적합"""
        return self.score >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "tool_name": self.tool_name,
            "score": self.score,
            "reason": self.reason,
            "approach": self.approach,
            "tool_type": self.tool_type,
        }


class ToolEvaluator:
    """도구 적합도 평가기

    Anthropic SDK를 사용하여 하이쿠 모델로 도구 적합도를 평가합니다.
    """

    def __init__(
        self,
        client: Any,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ):
        """
        Args:
            client: Anthropic 클라이언트 (AsyncAnthropic 또는 모킹된 객체)
            model: 사용할 모델 이름
            timeout: 요청 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            max_concurrent: 최대 동시 요청 수
        """
        self.client = client
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def evaluate_tool(
        self,
        tool: ToolDefinition,
        user_request: str,
    ) -> EvaluationResult:
        """단일 도구 평가.

        Args:
            tool: 평가할 도구
            user_request: 사용자 요청

        Returns:
            EvaluationResult 객체
        """
        prompt = build_evaluation_prompt(tool, user_request)

        for attempt in range(self.max_retries):
            try:
                async with self._semaphore:
                    response = await asyncio.wait_for(
                        self._call_api(prompt),
                        timeout=self.timeout,
                    )
                return parse_evaluation_response(response, tool.name, tool.tool_type)

            except asyncio.TimeoutError:
                logger.warning(f"도구 평가 타임아웃: {tool.name}")
                return EvaluationResult(
                    tool_name=tool.name,
                    score=0,
                    reason="평가 타임아웃",
                    approach="",
                    tool_type=tool.tool_type,
                )

            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "rate_limit" in error_str or "rate limit" in error_str

                if is_rate_limit and attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)  # 지수 백오프
                    logger.info(f"Rate limit, {delay}초 후 재시도: {tool.name}")
                    await asyncio.sleep(delay)
                    continue

                logger.warning(f"도구 평가 오류 ({tool.name}): {e}")
                return EvaluationResult(
                    tool_name=tool.name,
                    score=0,
                    reason=f"평가 오류: {str(e)[:50]}",
                    approach="",
                    tool_type=tool.tool_type,
                )

        return EvaluationResult(
            tool_name=tool.name,
            score=0,
            reason="최대 재시도 초과",
            approach="",
            tool_type=tool.tool_type,
        )

    async def _call_api(self, prompt: str) -> str:
        """API 호출.

        Args:
            prompt: 프롬프트

        Returns:
            모델 응답 텍스트
        """
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=800,  # 발췌 부분을 담기 위해 증가
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def evaluate_all(
        self,
        tools: list[ToolDefinition],
        user_request: str,
    ) -> list[EvaluationResult]:
        """모든 도구 병렬 평가.

        Args:
            tools: 평가할 도구 목록
            user_request: 사용자 요청

        Returns:
            EvaluationResult 리스트
        """
        tasks = [
            self.evaluate_tool(tool, user_request)
            for tool in tools
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외를 기본 결과로 변환
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"평가 실패 ({tools[i].name}): {result}")
                processed_results.append(
                    EvaluationResult(
                        tool_name=tools[i].name,
                        score=0,
                        reason=f"평가 실패: {str(result)[:50]}",
                        approach="",
                        tool_type=tools[i].tool_type,
                    )
                )
            else:
                processed_results.append(result)

        return processed_results
