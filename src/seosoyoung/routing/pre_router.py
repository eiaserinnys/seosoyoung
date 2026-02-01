"""PreRouter - 전체 사전 라우팅 파이프라인

loader, evaluator, aggregator를 조합하여 사용자 요청에 가장 적합한
도구를 결정하는 오케스트레이션 클래스.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import asyncio
import logging
import time

from .loader import ToolLoader, ToolDefinition
from .evaluator import ToolEvaluator, EvaluationResult
from .aggregator import ResultAggregator, AggregationResult


logger = logging.getLogger(__name__)

# 기본 설정
DEFAULT_MODEL = "claude-3-5-haiku-latest"
DEFAULT_TIMEOUT = 10.0
DEFAULT_THRESHOLD = 5
DEFAULT_MAX_CONCURRENT = 5


@dataclass
class RoutingResult:
    """라우팅 결과"""

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

        # 임계값 이상 도구 목록
        tools_list = []
        for i, tool_info in enumerate(self.suitable_tools, 1):
            marker = "👉" if tool_info["name"] == self.selected_tool else "  "
            tools_list.append(
                f"{marker} {i}. **{tool_info['name']}** ({tool_info['type']}) - {tool_info['score']}점\n"
                f"   - 이유: {tool_info['reason']}\n"
                f"   - 접근법: {tool_info['approach']}"
            )

        tools_text = "\n".join(tools_list)

        return f"""## 사전 라우팅 결과

### 추천 도구 (임계값 이상, 점수 순)

{tools_text}

### 요약
{self.summary}

위 정보를 참고하여 가장 적합한 도구나 접근 방식을 선택하세요."""


class PreRouter:
    """사전 라우팅 파이프라인

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
            enabled: 라우팅 활성화 여부
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

    async def route(self, user_request: str) -> RoutingResult:
        """사용자 요청에 대한 최적 도구 결정.

        Args:
            user_request: 사용자 요청 텍스트

        Returns:
            RoutingResult 객체
        """
        if not self.enabled:
            return RoutingResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary="라우팅이 비활성화되어 있습니다.",
                approach="",
                all_scores={},
                evaluation_time_ms=0.0,
                suitable_tools=[],
            )

        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self._route_internal(user_request),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"라우팅 타임아웃: {elapsed_ms:.1f}ms")
            return RoutingResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary="라우팅 타임아웃이 발생했습니다.",
                approach="",
                all_scores={},
                evaluation_time_ms=elapsed_ms,
                error="timeout",
                suitable_tools=[],
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"라우팅 오류: {e}")
            return RoutingResult(
                selected_tool=None,
                tool_type=None,
                confidence=0.0,
                summary=f"라우팅 오류: {str(e)[:100]}",
                approach="",
                all_scores={},
                evaluation_time_ms=elapsed_ms,
                error=str(e),
                suitable_tools=[],
            )

    async def _route_internal(self, user_request: str) -> RoutingResult:
        """내부 라우팅 로직"""
        start_time = time.perf_counter()

        # 1. 도구 목록 로드
        tools = self.get_tools()

        if not tools:
            return RoutingResult(
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

        return RoutingResult(
            selected_tool=agg_result.selected_tool,
            tool_type=tool_type,
            confidence=agg_result.confidence,
            summary=agg_result.summary,
            approach=agg_result.recommended_approach,
            all_scores=agg_result.all_scores,
            evaluation_time_ms=elapsed_ms,
            suitable_tools=suitable_tools_with_type,
        )

    def route_sync(self, user_request: str) -> RoutingResult:
        """동기 버전의 라우팅.

        Args:
            user_request: 사용자 요청 텍스트

        Returns:
            RoutingResult 객체
        """
        return asyncio.run(self.route(user_request))
