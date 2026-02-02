"""결과 집계기

개별 평가 결과를 종합하여 최적 도구를 선택하고 요약을 생성하는 모듈.
"""

from dataclasses import dataclass, field
from typing import Any
import logging

from .evaluator import EvaluationResult


logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 5


def _tool_type_priority(tool_type: str) -> int:
    """도구 타입 우선순위 반환 (낮을수록 우선).

    에이전트를 스킬보다 우선합니다.
    """
    priorities = {"agent": 0, "skill": 1, "unknown": 2}
    return priorities.get(tool_type, 2)


def rank_results(results: list[EvaluationResult]) -> list[EvaluationResult]:
    """평가 결과를 점수 기준으로 정렬.

    Args:
        results: 평가 결과 리스트

    Returns:
        점수 내림차순 정렬된 리스트 (동점 시 에이전트 우선, 그 다음 이름 순)
    """
    return sorted(
        results,
        key=lambda r: (-r.score, _tool_type_priority(r.tool_type), r.tool_name),
    )


def select_best_tool(
    results: list[EvaluationResult],
    threshold: int = DEFAULT_THRESHOLD,
) -> EvaluationResult | None:
    """최적 도구 선택.

    Args:
        results: 평가 결과 리스트
        threshold: 최소 적합도 임계값

    Returns:
        가장 높은 점수의 EvaluationResult 또는 None (모두 임계값 미만일 경우)
    """
    if not results:
        return None

    ranked = rank_results(results)
    best = ranked[0]

    if best.score >= threshold:
        return best

    return None


def build_summary_prompt(
    results: list[EvaluationResult],
    user_request: str,
    selected_tool: str | None,
) -> str:
    """요약 생성 프롬프트.

    Args:
        results: 평가 결과 리스트
        user_request: 사용자 요청
        selected_tool: 선택된 도구 이름 (없으면 None)

    Returns:
        요약 생성 프롬프트
    """
    ranked = rank_results(results)
    scores_text = "\n".join(
        f"- {r.tool_name}: {r.score}점 - {r.reason}"
        for r in ranked[:5]  # 상위 5개만
    )

    if selected_tool:
        selected_result = next(
            (r for r in results if r.tool_name == selected_tool), None
        )
        approach_text = (
            f"선택된 도구의 접근 방식: {selected_result.approach}"
            if selected_result
            else ""
        )
        instruction = f"""선택된 도구 `{selected_tool}`이(가) 이 요청을 처리하기에 가장 적합한 이유를
1-2문장으로 간결하게 설명해주세요."""
    else:
        approach_text = ""
        instruction = """적합한 도구가 없는 이유와 사용자 요청을 어떻게 처리해야 할지
1-2문장으로 설명해주세요."""

    return f"""다음 정보를 바탕으로 Recall 결정을 요약해주세요.

## 사용자 요청
"{user_request}"

## 도구별 평가 점수
{scores_text}

{approach_text}

## 지침
{instruction}

간결하게 한국어로 응답해주세요."""


@dataclass
class AggregationResult:
    """집계 결과"""

    selected_tool: str | None
    confidence: float
    summary: str
    all_scores: dict[str, int]
    recommended_approach: str = ""
    suitable_tools: list[dict[str, Any]] = field(default_factory=list)  # 임계값 이상 도구들

    @property
    def has_suitable_tool(self) -> bool:
        """적합한 도구가 있는지 여부"""
        return self.selected_tool is not None

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "selected_tool": self.selected_tool,
            "confidence": self.confidence,
            "summary": self.summary,
            "all_scores": self.all_scores,
            "recommended_approach": self.recommended_approach,
            "suitable_tools": self.suitable_tools,
        }

    @classmethod
    def from_evaluation_results(
        cls,
        results: list[EvaluationResult],
        user_request: str,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> "AggregationResult":
        """평가 결과에서 집계 결과 생성.

        Args:
            results: 평가 결과 리스트
            user_request: 사용자 요청
            threshold: 적합도 임계값

        Returns:
            AggregationResult 객체
        """
        if not results:
            return cls(
                selected_tool=None,
                confidence=0.0,
                summary="평가할 도구가 없습니다.",
                all_scores={},
                recommended_approach="",
                suitable_tools=[],
            )

        best = select_best_tool(results, threshold)
        all_scores = {r.tool_name: r.score for r in results}

        # 임계값 이상인 모든 도구 수집 (점수 순)
        ranked = rank_results(results)
        suitable_tools = [
            {
                "name": r.tool_name,
                "score": r.score,
                "reason": r.reason,
                "approach": r.approach,
            }
            for r in ranked if r.score >= threshold
        ]

        if best:
            confidence = best.score / 10.0
            if len(suitable_tools) > 1:
                summary = f"{len(suitable_tools)}개 도구가 적합합니다. 최고점: {best.tool_name} ({best.score}점)"
            else:
                summary = f"{best.tool_name}이(가) 가장 적합합니다. ({best.score}점)"
            approach = best.approach
        else:
            confidence = 0.0
            summary = "적합한 도구가 없습니다."
            approach = ""

        return cls(
            selected_tool=best.tool_name if best else None,
            confidence=confidence,
            summary=summary,
            all_scores=all_scores,
            recommended_approach=approach,
            suitable_tools=suitable_tools,
        )


class ResultAggregator:
    """결과 집계기

    평가 결과를 종합하여 최적 도구를 선택하고 요약을 생성합니다.
    """

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-3-5-haiku-latest",
        threshold: int = DEFAULT_THRESHOLD,
    ):
        """
        Args:
            client: Anthropic 클라이언트 (요약 생성용, 선택사항)
            model: 요약 생성에 사용할 모델
            threshold: 적합도 임계값
        """
        self.client = client
        self.model = model
        self.threshold = threshold

    def aggregate(
        self,
        results: list[EvaluationResult],
        user_request: str,
    ) -> AggregationResult:
        """평가 결과 집계 (요약 생성 없이).

        Args:
            results: 평가 결과 리스트
            user_request: 사용자 요청

        Returns:
            AggregationResult 객체
        """
        return AggregationResult.from_evaluation_results(
            results, user_request, self.threshold
        )

    async def aggregate_with_summary(
        self,
        results: list[EvaluationResult],
        user_request: str,
    ) -> AggregationResult:
        """평가 결과 집계 및 요약 생성.

        Args:
            results: 평가 결과 리스트
            user_request: 사용자 요청

        Returns:
            요약이 포함된 AggregationResult 객체
        """
        # 기본 집계
        base_result = self.aggregate(results, user_request)

        # 클라이언트가 없으면 기본 결과 반환
        if not self.client:
            return base_result

        # 요약 생성
        try:
            prompt = build_summary_prompt(
                results, user_request, base_result.selected_tool
            )
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            summary = response.content[0].text.strip()

            return AggregationResult(
                selected_tool=base_result.selected_tool,
                confidence=base_result.confidence,
                summary=summary,
                all_scores=base_result.all_scores,
                recommended_approach=base_result.recommended_approach,
            )
        except Exception as e:
            logger.warning(f"요약 생성 실패: {e}")
            # 폴백: 기본 요약 사용
            return base_result
