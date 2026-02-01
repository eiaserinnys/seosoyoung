"""결과 집계기 테스트 (TDD RED 단계)"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from seosoyoung.routing.aggregator import (
    AggregationResult,
    ResultAggregator,
    rank_results,
    select_best_tool,
    build_summary_prompt,
)
from seosoyoung.routing.evaluator import EvaluationResult


class TestRankResults:
    """결과 정렬 테스트"""

    def test_rank_by_score_descending(self):
        """점수 내림차순 정렬"""
        results = [
            EvaluationResult("tool_a", 5, "이유", "접근"),
            EvaluationResult("tool_b", 9, "이유", "접근"),
            EvaluationResult("tool_c", 7, "이유", "접근"),
        ]

        ranked = rank_results(results)

        assert ranked[0].tool_name == "tool_b"  # 9점
        assert ranked[1].tool_name == "tool_c"  # 7점
        assert ranked[2].tool_name == "tool_a"  # 5점

    def test_rank_handles_tie_by_name(self):
        """동점 시 같은 타입이면 이름 순으로 정렬 (일관성 보장)"""
        results = [
            EvaluationResult("zz_tool", 8, "이유", "접근", tool_type="agent"),
            EvaluationResult("aa_tool", 8, "이유", "접근", tool_type="agent"),
            EvaluationResult("mm_tool", 8, "이유", "접근", tool_type="agent"),
        ]

        ranked = rank_results(results)

        # 동점일 경우 이름 알파벳 순
        assert ranked[0].tool_name == "aa_tool"
        assert ranked[1].tool_name == "mm_tool"
        assert ranked[2].tool_name == "zz_tool"

    def test_rank_handles_tie_agent_over_skill(self):
        """동점 시 에이전트가 스킬보다 우선"""
        results = [
            EvaluationResult("skill_a", 9, "이유", "접근", tool_type="skill"),
            EvaluationResult("agent_z", 9, "이유", "접근", tool_type="agent"),
            EvaluationResult("skill_b", 9, "이유", "접근", tool_type="skill"),
        ]

        ranked = rank_results(results)

        # 동점일 경우 에이전트 우선, 그 다음 이름 순
        assert ranked[0].tool_name == "agent_z"  # agent 우선
        assert ranked[1].tool_name == "skill_a"  # 스킬 중 이름 순
        assert ranked[2].tool_name == "skill_b"

    def test_rank_empty_list(self):
        """빈 리스트 처리"""
        ranked = rank_results([])
        assert ranked == []


class TestSelectBestTool:
    """최적 도구 선택 테스트"""

    def test_select_highest_score(self):
        """가장 높은 점수의 도구 선택"""
        results = [
            EvaluationResult("lore", 9, "캐릭터 정보에 적합", "설정 파일 조회"),
            EvaluationResult("slackbot-dev", 3, "관련 없음", ""),
            EvaluationResult("search-glossary", 7, "부분적 적합", "용어집 검색"),
        ]

        best = select_best_tool(results)

        assert best is not None
        assert best.tool_name == "lore"
        assert best.score == 9

    def test_select_none_when_all_below_threshold(self):
        """모든 점수가 임계값 미만일 때 None 반환"""
        results = [
            EvaluationResult("tool_a", 3, "이유", "접근"),
            EvaluationResult("tool_b", 2, "이유", "접근"),
            EvaluationResult("tool_c", 4, "이유", "접근"),
        ]

        best = select_best_tool(results, threshold=5)

        assert best is None

    def test_select_with_custom_threshold(self):
        """커스텀 임계값 적용"""
        results = [
            EvaluationResult("tool_a", 6, "이유", "접근"),
            EvaluationResult("tool_b", 7, "이유", "접근"),
        ]

        # 임계값 8이면 둘 다 부적합
        best = select_best_tool(results, threshold=8)
        assert best is None

        # 임계값 6이면 tool_b 선택
        best = select_best_tool(results, threshold=6)
        assert best.tool_name == "tool_b"

    def test_select_from_empty_list(self):
        """빈 리스트에서 선택"""
        best = select_best_tool([])
        assert best is None


class TestBuildSummaryPrompt:
    """요약 프롬프트 생성 테스트"""

    def test_build_prompt_with_selected_tool(self):
        """선택된 도구가 있을 때 프롬프트"""
        results = [
            EvaluationResult("lore", 9, "캐릭터 정보 요청", "설정 파일 조회"),
            EvaluationResult("search", 6, "검색 가능", "용어집 검색"),
        ]
        user_request = "펜릭스 성격 알려줘"

        prompt = build_summary_prompt(results, user_request, selected_tool="lore")

        assert "lore" in prompt
        assert "펜릭스 성격" in prompt
        assert "9" in prompt  # 점수

    def test_build_prompt_without_selected_tool(self):
        """선택된 도구가 없을 때 프롬프트"""
        results = [
            EvaluationResult("tool_a", 3, "낮은 적합도", ""),
            EvaluationResult("tool_b", 2, "낮은 적합도", ""),
        ]
        user_request = "특이한 요청"

        prompt = build_summary_prompt(results, user_request, selected_tool=None)

        assert "특이한 요청" in prompt
        # 적합한 도구가 없다는 내용이 있어야 함


class TestAggregationResult:
    """AggregationResult 데이터 클래스 테스트"""

    def test_create_aggregation_result(self):
        """AggregationResult 생성"""
        result = AggregationResult(
            selected_tool="lore",
            confidence=0.9,
            summary="캐릭터 정보 요청이므로 lore 에이전트가 가장 적합합니다.",
            all_scores={"lore": 9, "search": 6, "dev": 3},
            recommended_approach="설정 파일에서 펜릭스 정보를 조회합니다.",
        )

        assert result.selected_tool == "lore"
        assert result.confidence == 0.9
        assert result.has_suitable_tool

    def test_no_suitable_tool(self):
        """적합한 도구가 없는 경우"""
        result = AggregationResult(
            selected_tool=None,
            confidence=0.0,
            summary="적합한 도구가 없습니다.",
            all_scores={"tool_a": 2, "tool_b": 3},
            recommended_approach="",
        )

        assert result.selected_tool is None
        assert not result.has_suitable_tool

    def test_to_dict(self):
        """딕셔너리 변환"""
        result = AggregationResult(
            selected_tool="lore",
            confidence=0.85,
            summary="요약",
            all_scores={"lore": 9},
            recommended_approach="접근",
        )
        d = result.to_dict()

        assert d["selected_tool"] == "lore"
        assert d["confidence"] == 0.85
        assert d["summary"] == "요약"
        assert d["all_scores"] == {"lore": 9}

    def test_confidence_from_score(self):
        """점수에서 신뢰도 계산"""
        # 10점 = 1.0 신뢰도
        result = AggregationResult.from_evaluation_results(
            [EvaluationResult("tool", 10, "", "")],
            "test",
        )
        assert result.confidence == 1.0

        # 5점 = 0.5 신뢰도
        result = AggregationResult.from_evaluation_results(
            [EvaluationResult("tool", 5, "", "")],
            "test",
        )
        assert result.confidence == 0.5


class TestResultAggregator:
    """ResultAggregator 테스트"""

    @pytest.fixture
    def mock_client(self):
        """Anthropic 클라이언트 모킹"""
        client = MagicMock()
        return client

    @pytest.fixture
    def sample_results(self):
        """테스트용 평가 결과"""
        return [
            EvaluationResult("lore", 9, "캐릭터 정보에 적합", "설정 파일 조회"),
            EvaluationResult("slackbot-dev", 2, "관련 없음", ""),
            EvaluationResult("search-glossary", 7, "용어집 검색 가능", "검색 수행"),
        ]

    def test_aggregate_selects_best_tool(self, sample_results):
        """최적 도구 선택"""
        aggregator = ResultAggregator()
        result = aggregator.aggregate(sample_results, "펜릭스 성격 알려줘")

        assert result.selected_tool == "lore"
        assert result.confidence >= 0.8  # 9점이므로

    def test_aggregate_with_no_suitable_tools(self):
        """적합한 도구가 없을 때"""
        results = [
            EvaluationResult("tool_a", 2, "부적합", ""),
            EvaluationResult("tool_b", 3, "부적합", ""),
        ]

        aggregator = ResultAggregator(threshold=5)
        result = aggregator.aggregate(results, "특이한 요청")

        assert result.selected_tool is None
        assert not result.has_suitable_tool

    def test_aggregate_includes_all_scores(self, sample_results):
        """모든 점수 포함"""
        aggregator = ResultAggregator()
        result = aggregator.aggregate(sample_results, "테스트")

        assert "lore" in result.all_scores
        assert "slackbot-dev" in result.all_scores
        assert "search-glossary" in result.all_scores
        assert result.all_scores["lore"] == 9
        assert result.all_scores["slackbot-dev"] == 2

    @pytest.mark.asyncio
    async def test_aggregate_with_summary_generation(self, mock_client, sample_results):
        """요약 생성 포함 집계"""
        # 요약 생성 응답 모킹
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="사용자가 캐릭터 정보를 요청했으므로 lore 에이전트가 가장 적합합니다.")
        ]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        aggregator = ResultAggregator(client=mock_client)
        result = await aggregator.aggregate_with_summary(
            sample_results,
            "펜릭스 성격 알려줘",
        )

        assert result.selected_tool == "lore"
        assert "lore" in result.summary.lower() or "캐릭터" in result.summary

    @pytest.mark.asyncio
    async def test_aggregate_summary_fallback_on_error(self, mock_client, sample_results):
        """요약 생성 실패 시 폴백"""
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        aggregator = ResultAggregator(client=mock_client)
        result = await aggregator.aggregate_with_summary(
            sample_results,
            "테스트 요청",
        )

        # 오류 시에도 기본 결과는 반환
        assert result.selected_tool == "lore"
        assert result.summary != ""  # 폴백 요약

    def test_aggregate_empty_results(self):
        """빈 결과 집계"""
        aggregator = ResultAggregator()
        result = aggregator.aggregate([], "테스트")

        assert result.selected_tool is None
        assert result.all_scores == {}


class TestResultAggregatorWithThreshold:
    """임계값 설정 테스트"""

    def test_custom_threshold(self):
        """커스텀 임계값"""
        aggregator = ResultAggregator(threshold=7)
        assert aggregator.threshold == 7

    def test_default_threshold_is_5(self):
        """기본 임계값은 5"""
        aggregator = ResultAggregator()
        assert aggregator.threshold == 5

    def test_threshold_affects_selection(self):
        """임계값이 선택에 영향"""
        results = [
            EvaluationResult("tool_a", 6, "이유", "접근"),
            EvaluationResult("tool_b", 5, "이유", "접근"),
        ]

        # 임계값 5: tool_a 선택
        aggregator = ResultAggregator(threshold=5)
        result = aggregator.aggregate(results, "테스트")
        assert result.selected_tool == "tool_a"

        # 임계값 7: 선택 없음
        aggregator = ResultAggregator(threshold=7)
        result = aggregator.aggregate(results, "테스트")
        assert result.selected_tool is None
