"""하이쿠 평가 클라이언트 테스트 (TDD RED 단계)"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from seosoyoung.routing.evaluator import (
    EvaluationResult,
    ToolEvaluator,
    build_evaluation_prompt,
    parse_evaluation_response,
)
from seosoyoung.routing.loader import ToolDefinition, AgentDefinition, SkillDefinition


class TestBuildEvaluationPrompt:
    """평가 프롬프트 생성 테스트"""

    def test_build_prompt_with_agent(self):
        """에이전트 평가 프롬프트 생성"""
        tool = AgentDefinition(
            name="lore",
            description="캐릭터나 배경 설정에 대해 문의하거나 수정을 요청할 때 사용",
            file_path=Path(".claude/agents/lore.md"),
        )
        user_request = "펜릭스 성격 알려줘"

        prompt = build_evaluation_prompt(tool, user_request)

        assert "lore" in prompt
        assert "캐릭터나 배경 설정" in prompt
        assert "펜릭스 성격 알려줘" in prompt
        assert "agent" in prompt.lower()

    def test_build_prompt_with_skill(self):
        """스킬 평가 프롬프트 생성"""
        tool = SkillDefinition(
            name="search-glossary",
            description="용어집에서 캐릭터나 장소 정보를 검색",
            file_path=Path(".claude/skills/lore-search-glossary/SKILL.md"),
            allowed_tools=["Read", "Glob"],
        )
        user_request = "하니엘 누구야?"

        prompt = build_evaluation_prompt(tool, user_request)

        assert "search-glossary" in prompt
        assert "용어집" in prompt
        assert "하니엘 누구야?" in prompt

    def test_prompt_includes_scoring_instructions(self):
        """프롬프트에 점수 지침 포함"""
        tool = AgentDefinition(
            name="test",
            description="테스트",
            file_path=Path("test.md"),
        )
        prompt = build_evaluation_prompt(tool, "테스트 요청")

        # JSON 형식으로 응답하라는 지침 포함
        assert "JSON" in prompt or "json" in prompt
        assert "score" in prompt.lower()


class TestParseEvaluationResponse:
    """평가 응답 파싱 테스트"""

    def test_parse_valid_json_response(self):
        """유효한 JSON 응답 파싱"""
        response = json.dumps({
            "score": 8,
            "relevant_excerpts": [
                "캐릭터 정보를 관리합니다.",
                "설정 파일을 조회합니다."
            ],
            "approach": "캐릭터 설정 파일을 조회하여 정보를 제공합니다.",
        })

        result = parse_evaluation_response(response, "lore")

        assert result.tool_name == "lore"
        assert result.score == 8
        assert "캐릭터 정보" in result.reason
        assert "캐릭터 설정" in result.approach

    def test_parse_json_with_markdown_fence(self):
        """마크다운 코드 펜스로 감싼 JSON 파싱"""
        response = """```json
{
    "score": 7,
    "relevant_excerpts": ["적합한 도구입니다."],
    "approach": "직접 처리합니다."
}
```"""

        result = parse_evaluation_response(response, "test-tool")

        assert result.score == 7
        assert result.tool_name == "test-tool"

    def test_parse_score_out_of_range_clamped(self):
        """범위 밖 점수는 클램핑"""
        response = json.dumps({"score": 15, "relevant_excerpts": ["테스트"], "approach": "테스트"})
        result = parse_evaluation_response(response, "test")
        assert result.score == 10  # 최대값으로 클램핑

        response = json.dumps({"score": -5, "relevant_excerpts": ["테스트"], "approach": "테스트"})
        result = parse_evaluation_response(response, "test")
        assert result.score == 0  # 최소값으로 클램핑

    def test_parse_malformed_json_fallback(self):
        """잘못된 JSON은 정규식 폴백"""
        response = """
        이 도구의 적합도 점수는 6점입니다.
        이유: 부분적으로 관련이 있습니다.
        접근 방식: 기본 처리를 수행합니다.
        """

        result = parse_evaluation_response(response, "fallback-tool")

        # 폴백 시 기본값 또는 추출된 값
        assert result.tool_name == "fallback-tool"
        assert 0 <= result.score <= 10

    def test_parse_missing_fields_uses_defaults(self):
        """누락된 필드는 기본값 사용"""
        response = json.dumps({"score": 5})

        result = parse_evaluation_response(response, "test")

        assert result.score == 5
        # relevant_excerpts 없으면 빈 문자열
        assert result.reason == ""
        assert result.approach == "접근 방식 미정"  # 기본값


class TestEvaluationResult:
    """EvaluationResult 데이터 클래스 테스트"""

    def test_create_evaluation_result(self):
        """EvaluationResult 생성"""
        result = EvaluationResult(
            tool_name="lore",
            score=8,
            reason="캐릭터 정보 요청에 적합",
            approach="설정 파일 조회",
        )

        assert result.tool_name == "lore"
        assert result.score == 8
        assert result.is_suitable  # 5점 이상이면 적합

    def test_is_suitable_threshold(self):
        """적합 여부 임계값 테스트"""
        suitable = EvaluationResult("test", 5, "테스트", "테스트")
        assert suitable.is_suitable

        not_suitable = EvaluationResult("test", 4, "테스트", "테스트")
        assert not not_suitable.is_suitable

    def test_to_dict(self):
        """딕셔너리 변환"""
        result = EvaluationResult("lore", 8, "이유", "접근")
        d = result.to_dict()

        assert d["tool_name"] == "lore"
        assert d["score"] == 8
        assert d["reason"] == "이유"
        assert d["approach"] == "접근"


class TestToolEvaluator:
    """ToolEvaluator 테스트"""

    @pytest.fixture
    def mock_anthropic_client(self):
        """Anthropic 클라이언트 모킹"""
        client = MagicMock()
        client.messages = MagicMock()
        return client

    @pytest.fixture
    def sample_tools(self):
        """테스트용 도구 목록"""
        return [
            AgentDefinition(
                name="lore",
                description="캐릭터나 배경 설정 관련 작업",
                file_path=Path(".claude/agents/lore.md"),
            ),
            AgentDefinition(
                name="slackbot-dev",
                description="슬랙봇 개발 관련 작업",
                file_path=Path(".claude/agents/slackbot-dev.md"),
            ),
            SkillDefinition(
                name="search-glossary",
                description="용어집 검색",
                file_path=Path(".claude/skills/search-glossary/SKILL.md"),
                allowed_tools=["Read"],
            ),
        ]

    @pytest.mark.asyncio
    async def test_evaluate_single_tool(self, mock_anthropic_client, sample_tools):
        """단일 도구 평가"""
        # 응답 모킹
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "score": 9,
                "reason": "캐릭터 정보 요청에 매우 적합",
                "approach": "설정 파일 조회",
            }))
        ]

        async def mock_create(*args, **kwargs):
            return mock_response

        mock_anthropic_client.messages.create = AsyncMock(side_effect=mock_create)

        evaluator = ToolEvaluator(client=mock_anthropic_client)
        result = await evaluator.evaluate_tool(
            sample_tools[0],  # lore 에이전트
            "펜릭스 성격 알려줘",
        )

        assert result.tool_name == "lore"
        assert result.score == 9
        assert result.is_suitable

    @pytest.mark.asyncio
    async def test_evaluate_all_tools_parallel(self, mock_anthropic_client, sample_tools):
        """모든 도구 병렬 평가"""
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = MagicMock()
            # 각 도구에 대해 다른 점수 반환
            scores = [9, 3, 7]
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": scores[(call_count - 1) % 3],
                    "reason": f"테스트 이유 {call_count}",
                    "approach": f"테스트 접근 {call_count}",
                }))
            ]
            return mock_response

        mock_anthropic_client.messages.create = AsyncMock(side_effect=mock_create)

        evaluator = ToolEvaluator(client=mock_anthropic_client)
        results = await evaluator.evaluate_all(
            sample_tools,
            "펜릭스 성격 알려줘",
        )

        assert len(results) == 3
        assert call_count == 3  # 3개 도구 모두 호출됨

    @pytest.mark.asyncio
    async def test_evaluate_with_timeout(self, mock_anthropic_client, sample_tools):
        """타임아웃 처리"""
        async def slow_create(*args, **kwargs):
            await asyncio.sleep(10)  # 긴 대기 시간

        mock_anthropic_client.messages.create = AsyncMock(side_effect=slow_create)

        evaluator = ToolEvaluator(client=mock_anthropic_client, timeout=0.1)

        # 타임아웃 시 기본값 반환 (점수 0)
        result = await evaluator.evaluate_tool(
            sample_tools[0],
            "테스트",
        )

        assert result.score == 0  # 타임아웃 시 기본 점수

    @pytest.mark.asyncio
    async def test_evaluate_with_api_error(self, mock_anthropic_client, sample_tools):
        """API 오류 처리"""
        mock_anthropic_client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        evaluator = ToolEvaluator(client=mock_anthropic_client)
        result = await evaluator.evaluate_tool(
            sample_tools[0],
            "테스트",
        )

        assert result.score == 0  # 오류 시 기본 점수
        assert "error" in result.reason.lower() or result.reason == ""

    @pytest.mark.asyncio
    async def test_evaluate_with_rate_limit_retry(self, mock_anthropic_client, sample_tools):
        """Rate limit 시 재시도"""
        call_count = 0

        async def rate_limited_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("rate_limit_exceeded")
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": 8,
                    "reason": "성공",
                    "approach": "테스트",
                }))
            ]
            return mock_response

        mock_anthropic_client.messages.create = AsyncMock(side_effect=rate_limited_create)

        evaluator = ToolEvaluator(
            client=mock_anthropic_client,
            max_retries=3,
            retry_delay=0.01,
        )
        result = await evaluator.evaluate_tool(sample_tools[0], "테스트")

        assert result.score == 8
        assert call_count == 3  # 2번 실패 후 3번째에 성공

    @pytest.mark.asyncio
    async def test_batch_evaluation(self, mock_anthropic_client, sample_tools):
        """배치 평가 (동시 요청 수 제한)"""
        active_calls = 0
        max_concurrent = 0

        async def tracked_create(*args, **kwargs):
            nonlocal active_calls, max_concurrent
            active_calls += 1
            max_concurrent = max(max_concurrent, active_calls)
            await asyncio.sleep(0.01)
            active_calls -= 1
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": 5,
                    "reason": "테스트",
                    "approach": "테스트",
                }))
            ]
            return mock_response

        mock_anthropic_client.messages.create = AsyncMock(side_effect=tracked_create)

        evaluator = ToolEvaluator(
            client=mock_anthropic_client,
            max_concurrent=2,  # 동시 최대 2개
        )

        # 5개 도구로 확장
        tools = sample_tools + sample_tools[:2]
        results = await evaluator.evaluate_all(tools, "테스트")

        assert len(results) == 5
        assert max_concurrent <= 2  # 동시 요청이 2개를 초과하지 않음


class TestToolEvaluatorWithModel:
    """모델 설정 테스트"""

    def test_default_model_is_haiku(self):
        """기본 모델은 하이쿠"""
        evaluator = ToolEvaluator(client=MagicMock())
        assert "haiku" in evaluator.model.lower()

    def test_custom_model(self):
        """커스텀 모델 설정"""
        evaluator = ToolEvaluator(
            client=MagicMock(),
            model="claude-3-sonnet-20240229",
        )
        assert evaluator.model == "claude-3-sonnet-20240229"
