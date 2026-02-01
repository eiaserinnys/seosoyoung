"""사전 라우팅 모듈

Claude Code 호출 전에 하이쿠 모델로 에이전트/스킬 적합도를 평가하여
최적의 접근 방식을 미리 결정하는 파이프라인.
"""

from .loader import (
    ToolDefinition,
    AgentDefinition,
    SkillDefinition,
    ToolLoader,
    parse_frontmatter,
)
from .evaluator import (
    EvaluationResult,
    ToolEvaluator,
    build_evaluation_prompt,
    parse_evaluation_response,
)
from .aggregator import (
    AggregationResult,
    ResultAggregator,
    rank_results,
    select_best_tool,
    build_summary_prompt,
)

__all__ = [
    # loader
    "ToolDefinition",
    "AgentDefinition",
    "SkillDefinition",
    "ToolLoader",
    "parse_frontmatter",
    # evaluator
    "EvaluationResult",
    "ToolEvaluator",
    "build_evaluation_prompt",
    "parse_evaluation_response",
    # aggregator
    "AggregationResult",
    "ResultAggregator",
    "rank_results",
    "select_best_tool",
    "build_summary_prompt",
]
