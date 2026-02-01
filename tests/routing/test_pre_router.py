"""PreRouter 클래스 테스트 (TDD RED 단계)"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from seosoyoung.routing.pre_router import (
    PreRouter,
    RoutingResult,
)
from seosoyoung.routing.loader import AgentDefinition, SkillDefinition
from seosoyoung.routing.evaluator import EvaluationResult
from seosoyoung.routing.aggregator import AggregationResult


class TestRoutingResult:
    """RoutingResult 데이터 클래스 테스트"""

    def test_create_routing_result(self):
        """RoutingResult 생성"""
        result = RoutingResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.9,
            summary="캐릭터 정보 요청에 lore 에이전트가 적합합니다.",
            approach="설정 파일에서 정보를 조회합니다.",
            all_scores={"lore": 9, "search": 6},
            evaluation_time_ms=150.5,
        )

        assert result.selected_tool == "lore"
        assert result.tool_type == "agent"
        assert result.confidence == 0.9
        assert result.has_recommendation

    def test_no_recommendation(self):
        """추천 도구가 없는 경우"""
        result = RoutingResult(
            selected_tool=None,
            tool_type=None,
            confidence=0.0,
            summary="적합한 도구가 없습니다.",
            approach="",
            all_scores={"tool_a": 2, "tool_b": 3},
            evaluation_time_ms=100.0,
        )

        assert not result.has_recommendation

    def test_to_dict(self):
        """딕셔너리 변환"""
        result = RoutingResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.85,
            summary="요약",
            approach="접근",
            all_scores={"lore": 9},
            evaluation_time_ms=123.4,
        )
        d = result.to_dict()

        assert d["selected_tool"] == "lore"
        assert d["tool_type"] == "agent"
        assert d["evaluation_time_ms"] == 123.4

    def test_to_prompt_injection(self):
        """Claude Code 프롬프트에 주입할 텍스트 생성"""
        result = RoutingResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.9,
            summary="캐릭터 정보 요청입니다.",
            approach="설정 파일 조회",
            all_scores={"lore": 9, "search": 6},
            evaluation_time_ms=100.0,
        )

        injection = result.to_prompt_injection()

        assert "lore" in injection
        assert "agent" in injection.lower() or "에이전트" in injection


class TestPreRouter:
    """PreRouter 테스트"""

    @pytest.fixture
    def mock_client(self):
        """Anthropic 클라이언트 모킹"""
        client = MagicMock()
        return client

    @pytest.fixture
    def sample_workspace(self, tmp_path):
        """테스트용 워크스페이스"""
        # 에이전트 생성
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "lore.md").write_text(
            """---
name: lore
description: 캐릭터나 배경 설정 관련 작업
---
# 지침
""",
            encoding="utf-8",
        )
        (agents_dir / "slackbot-dev.md").write_text(
            """---
name: slackbot-dev
description: 슬랙봇 개발 작업
---
# 지침
""",
            encoding="utf-8",
        )

        # 스킬 생성
        skill_dir = tmp_path / ".claude" / "skills" / "search-glossary"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: search-glossary
description: 용어집 검색
allowed-tools: Read, Glob
---
# 검색
""",
            encoding="utf-8",
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_route_full_pipeline(self, mock_client, sample_workspace):
        """전체 파이프라인 테스트"""
        # 평가 응답 모킹
        call_count = 0
        scores = [9, 3, 7]  # lore, slackbot-dev, search-glossary

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            score = scores[call_count % 3]
            call_count += 1
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": score,
                    "reason": f"테스트 이유 (점수: {score})",
                    "approach": "테스트 접근",
                }))
            ]
            return mock_response

        mock_client.messages.create = AsyncMock(side_effect=mock_create)

        router = PreRouter(
            workspace_path=sample_workspace,
            client=mock_client,
        )

        result = await router.route("펜릭스 성격 알려줘")

        assert result.selected_tool == "lore"
        assert result.tool_type == "agent"
        assert result.confidence >= 0.8
        assert result.evaluation_time_ms > 0

    @pytest.mark.asyncio
    async def test_route_no_suitable_tool(self, mock_client, sample_workspace):
        """적합한 도구가 없을 때"""
        async def low_score_create(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": 2,
                    "reason": "관련 없음",
                    "approach": "",
                }))
            ]
            return mock_response

        mock_client.messages.create = AsyncMock(side_effect=low_score_create)

        router = PreRouter(
            workspace_path=sample_workspace,
            client=mock_client,
            threshold=5,
        )

        result = await router.route("특이한 요청")

        assert result.selected_tool is None
        assert not result.has_recommendation

    @pytest.mark.asyncio
    async def test_route_with_timeout(self, mock_client, sample_workspace):
        """전체 파이프라인 타임아웃"""
        async def slow_create(*args, **kwargs):
            await asyncio.sleep(10)

        mock_client.messages.create = AsyncMock(side_effect=slow_create)

        router = PreRouter(
            workspace_path=sample_workspace,
            client=mock_client,
            timeout=0.1,
        )

        result = await router.route("테스트")

        # 타임아웃 시 폴백 결과 (개별 도구 타임아웃 또는 전체 타임아웃)
        assert result.selected_tool is None
        # 모든 점수가 0이어야 함 (타임아웃으로 인해)
        assert all(score == 0 for score in result.all_scores.values())

    @pytest.mark.asyncio
    async def test_route_with_api_failure_fallback(self, mock_client, sample_workspace):
        """API 실패 시 폴백"""
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        router = PreRouter(
            workspace_path=sample_workspace,
            client=mock_client,
        )

        result = await router.route("테스트")

        # API 실패 시에도 결과 반환 (모든 도구 점수 0)
        assert result is not None
        assert result.selected_tool is None

    @pytest.mark.asyncio
    async def test_route_empty_workspace(self, mock_client, tmp_path):
        """빈 워크스페이스"""
        router = PreRouter(
            workspace_path=tmp_path,
            client=mock_client,
        )

        result = await router.route("테스트")

        assert result.selected_tool is None
        assert len(result.all_scores) == 0


class TestPreRouterConfiguration:
    """PreRouter 설정 테스트"""

    def test_default_configuration(self, tmp_path):
        """기본 설정"""
        router = PreRouter(workspace_path=tmp_path)

        assert router.model == "claude-3-5-haiku-latest"
        assert router.timeout == 10.0
        assert router.threshold == 5

    def test_custom_configuration(self, tmp_path):
        """커스텀 설정"""
        router = PreRouter(
            workspace_path=tmp_path,
            model="claude-3-sonnet",
            timeout=5.0,
            threshold=7,
        )

        assert router.model == "claude-3-sonnet"
        assert router.timeout == 5.0
        assert router.threshold == 7

    def test_disabled_routing(self, tmp_path):
        """라우팅 비활성화"""
        router = PreRouter(
            workspace_path=tmp_path,
            enabled=False,
        )

        assert not router.enabled


class TestPreRouterSync:
    """동기 인터페이스 테스트"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        return client

    def test_route_sync(self, mock_client, tmp_path):
        """동기 route 메서드"""
        # 에이전트 설정
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test.md").write_text(
            """---
name: test
description: 테스트 에이전트
---
""",
            encoding="utf-8",
        )

        async def mock_create(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.content = [
                MagicMock(text=json.dumps({
                    "score": 8,
                    "reason": "적합",
                    "approach": "처리",
                }))
            ]
            return mock_response

        mock_client.messages.create = AsyncMock(side_effect=mock_create)

        router = PreRouter(
            workspace_path=tmp_path,
            client=mock_client,
        )

        # 동기 호출
        result = router.route_sync("테스트 요청")

        assert result.selected_tool == "test"


class TestPreRouterCaching:
    """도구 목록 캐싱 테스트"""

    @pytest.fixture
    def sample_workspace(self, tmp_path):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "test.md").write_text(
            """---
name: test
description: 테스트
---
""",
            encoding="utf-8",
        )
        return tmp_path

    def test_tools_cached(self, sample_workspace):
        """도구 목록 캐싱"""
        router = PreRouter(workspace_path=sample_workspace)

        # 첫 번째 로드
        tools1 = router.get_tools()
        # 두 번째 로드 (캐시 사용)
        tools2 = router.get_tools()

        assert tools1 is tools2  # 같은 객체

    def test_cache_refresh(self, sample_workspace):
        """캐시 갱신"""
        router = PreRouter(workspace_path=sample_workspace)

        tools1 = router.get_tools()
        router.refresh_tools()
        tools2 = router.get_tools()

        assert tools1 is not tools2  # 다른 객체
