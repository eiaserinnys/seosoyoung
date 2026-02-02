"""Recall - 도구 선택 사전 분석 파이프라인

loader, evaluator, aggregator를 조합하여 사용자 요청에 가장 적합한
도구를 결정하는 오케스트레이션 클래스.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import asyncio
import logging
import os
import time

from .loader import ToolLoader, ToolDefinition
from .evaluator import ToolEvaluator, EvaluationResult
from .aggregator import ResultAggregator, AggregationResult


logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_MODEL = os.getenv("RECALL_MODEL", "claude-haiku-4-5")
DEFAULT_TIMEOUT = 10.0
DEFAULT_THRESHOLD = 5
DEFAULT_MAX_CONCURRENT = 5


@dataclass
class RecallResult:
    """Recall 결과"""

    selected_tool: str | None
    tool_type: str | None
    confidence: float
    summary: str
    approach: str
    all_scores: dict[str, int]
    evaluation_time_ms: float
    error: str | None = None
    suitable_tools: list[dict[str, Any]] = field(default_factory=list)  # 임계값 이상 도구들

    @property
    def has_recommendation(self) -> bool:
        """추천 도구가 있는지 여부"""
        return self.selected_tool is not None

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "selected_tool": self.selected_tool,
            "tool_type": self.tool_type,
            "confidence": self.confidence,
            "summary": self.summary,
            "approach": self.approach,
            "all_scores": self.all_scores,
            "evaluation_time_ms": self.evaluation_time_ms,
            "error": self.error,
            "suitable_tools": self.suitable_tools,
        }

    def to_prompt_injection(self) -> str:
        """Claude Code 프롬프트에 주입할 텍스트 생성"""
        if not self.suitable_tools:
            return ""

        # 도구별 섹션 생성
        tool_sections = []
        for tool_info in self.suitable_tools:
            section_lines = [
                f"## {tool_info['name']} ({tool_info['type']})",
                "",
                "### 설명",
                tool_info['approach'],
            ]

            # 발췌가 있으면 추가
            if tool_info.get('reason'):
                section_lines.extend([
                    "",
                    "### 발췌",
                    "```",
                    tool_info['reason'],
                    "```",
                ])

            tool_sections.append("\n".join(section_lines))

        tools_text = "\n\n".join(tool_sections)

        return f"""# 질문에 관련된 도구

아래는 에이전트와 스킬 정의 중 사용자의 요청과 연관된 맥락을 발췌한 것입니다.
사용자의 질문에 항상 정확하게 부합하는 에이전트나 도구가 존재하지 않는 경우가 있습니다.
그러나 그런 경우에도 기존의 에이전트나 도구가 사용자의 요청과 관련된 정보를 담고 있을 수 있습니다.
따라서 아래 발췌를 살펴보고 적절한 도구를 선택하여 작업을 진행합니다.
하나의 도구가 아니라 적합하다고 판단되는 도구를 모두 살펴보고 작업하는 것을 권장합니다.

{tools_text}"""


# 하위 호환성을 위한 별칭
RoutingResult = RecallResult


class Recall:
    """Recall - 도구 선택 사전 분석 파이프라인

    사용자 요청을 분석하여 가장 적합한 에이전트/스킬을 결정합니다.
    """

    def __init__(
        self,
        workspace_path: Path | str,
        client: Any = None,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        threshold: int = DEFAULT_THRESHOLD,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        enabled: bool = True,
    ):
        """
        Args:
            workspace_path: 워크스페이스 루트 경로
            client: Anthropic 클라이언트 (선택사항)
            model: 사용할 모델 이름
            timeout: 전체 파이프라인 타임아웃 (초)
            threshold: 적합도 임계값
            max_concurrent: 최대 동시 평가 수
            enabled: Recall 활성화 여부
        """
        self.workspace_path = Path(workspace_path)
        self.client = client
        self.model = model
        self.timeout = timeout
        self.threshold = threshold
        self.max_concurrent = max_concurrent
        self.enabled = enabled

        # 내부 컴포넌트
        self._loader = ToolLoader(self.workspace_path)
        self._tools_cache: list[ToolDefinition] | None = None

    def get_tools(self) -> list[ToolDefinition]:
        """도구 목록 로드 (캐싱)"""
        if self._tools_cache is None:
            self._tools_cache = self._loader.load_all()
        return self._tools_cache

    def refresh_tools(self) -> None:
        """도구 목록 캐시 갱신"""
        self._tools_cache = None

    async def analyze(self, user_request: str) -> RecallResult:
        """사용자 요청에 대한 최적 도구 결정.

        Args:
            user_request: 사용자 요청 텍스트

        Returns:
            RecallResult 객체
        """
        if not self.enabled:
            return RecallResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary="Recall이 비활성화되어 있습니다.",
                approach="",
                all_scores={},
                evaluation_time_ms=0.0,
                suitable_tools=[],
            )

        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self._analyze_internal(user_request),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"Recall 타임아웃: {elapsed_ms:.1f}ms")
            return RecallResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary="Recall 타임아웃이 발생했습니다.",
                approach="",
                all_scores={},
                evaluation_time_ms=elapsed_ms,
                error="timeout",
                suitable_tools=[],
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Recall 오류: {e}")
            return RecallResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary=f"Recall 오류: {str(e)[:100]}",
                approach="",
                all_scores={},
                evaluation_time_ms=elapsed_ms,
                error=str(e),
                suitable_tools=[],
            )

    async def _analyze_internal(self, user_request: str) -> RecallResult:
        """내부 분석 로직"""
        start_time = time.perf_counter()

        # 1. 도구 목록 로드
        tools = self.get_tools()

        if not tools:
            return RecallResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary="평가할 도구가 없습니다.",
                approach="",
                all_scores={},
                evaluation_time_ms=0.0,
                suitable_tools=[],
            )

        # 2. 평가 수행
        evaluator = ToolEvaluator(
            client=self.client,
            model=self.model,
            timeout=self.timeout / 2,  # 전체 타임아웃의 절반
            max_concurrent=self.max_concurrent,
        )

        eval_results = await evaluator.evaluate_all(tools, user_request)

        # 3. 결과 집계
        aggregator = ResultAggregator(
            client=self.client,
            model=self.model,
            threshold=self.threshold,
        )

        agg_result = aggregator.aggregate(eval_results, user_request)

        # 4. 결과 변환
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # 선택된 도구의 타입 결정
        tool_type = None
        if agg_result.selected_tool:
            for tool in tools:
                if tool.name == agg_result.selected_tool:
                    tool_type = tool.tool_type
                    break

        # suitable_tools에 타입 정보 추가
        tools_dict = {tool.name: tool.tool_type for tool in tools}
        suitable_tools_with_type = [
            {
                **tool_info,
                "type": tools_dict.get(tool_info["name"], "unknown"),
            }
            for tool_info in agg_result.suitable_tools
        ]

        return RecallResult(
            selected_tool=agg_result.selected_tool,
            tool_type=tool_type,
            confidence=agg_result.confidence,
            summary=agg_result.summary,
            approach=agg_result.recommended_approach,
            all_scores=agg_result.all_scores,
            evaluation_time_ms=elapsed_ms,
            suitable_tools=suitable_tools_with_type,
        )

    def analyze_sync(self, user_request: str) -> RecallResult:
        """동기 버전의 분석.

        Args:
            user_request: 사용자 요청 텍스트

        Returns:
            RecallResult 객체
        """
        return asyncio.run(self.analyze(user_request))

    # 하위 호환성을 위한 별칭
    async def route(self, user_request: str) -> RecallResult:
        """analyze()의 별칭 (하위 호환성)"""
        return await self.analyze(user_request)

    def route_sync(self, user_request: str) -> RecallResult:
        """analyze_sync()의 별칭 (하위 호환성)"""
        return self.analyze_sync(user_request)


# 하위 호환성을 위한 별칭
PreRouter = Recall
