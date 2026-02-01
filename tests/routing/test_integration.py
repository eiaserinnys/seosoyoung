"""사전 라우팅 통합 테스트

실제 Haiku API를 사용하는 통합 테스트입니다.
ANTHROPIC_API_KEY 환경변수가 설정되어 있어야 실행됩니다.

실행:
    pytest tests/routing/test_integration.py -v -s
    pytest tests/routing/test_integration.py -v -s -k "test_route_lore"
"""

import pytest
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

# 통합 테스트 전용 로거
integration_logger = logging.getLogger("routing.integration")


@dataclass
class ABTestResult:
    """A/B 테스트 결과 기록"""

    test_id: str
    timestamp: str
    user_request: str
    expected_tool: str
    expected_type: str
    actual_tool: Optional[str]
    actual_type: Optional[str]
    confidence: float
    all_scores: dict
    evaluation_time_ms: float
    is_correct: bool
    model: str = "claude-3-5-haiku-latest"
    threshold: int = 5
    error: Optional[str] = None

    def to_log_line(self) -> str:
        """JSONL 로그 라인 생성"""
        return json.dumps(asdict(self), ensure_ascii=False)


class ABTestLogger:
    """A/B 테스트 로깅 클래스"""

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path(__file__).parent.parent.parent / ".local" / "ab_test_logs"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[ABTestResult] = []

    def log(self, result: ABTestResult):
        """테스트 결과 기록"""
        self.results.append(result)

        # JSONL 파일에 기록
        log_file = self.log_dir / f"routing_ab_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(result.to_log_line() + "\n")

        # 콘솔 로깅
        status = "✅" if result.is_correct else "❌"
        integration_logger.info(
            f"{status} [{result.test_id}] {result.user_request[:30]}... "
            f"→ expected: {result.expected_tool}, actual: {result.actual_tool} "
            f"({result.evaluation_time_ms:.1f}ms)"
        )

    def get_summary(self) -> dict:
        """테스트 결과 요약"""
        if not self.results:
            return {"total": 0, "correct": 0, "accuracy": 0.0}

        correct = sum(1 for r in self.results if r.is_correct)
        total = len(self.results)
        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0.0,
            "avg_time_ms": sum(r.evaluation_time_ms for r in self.results) / total,
            "errors": sum(1 for r in self.results if r.error),
        }


# API 키 확인
def has_api_key() -> bool:
    """ANTHROPIC_API_KEY 환경변수 존재 여부"""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# pytest 마커
requires_api_key = pytest.mark.skipif(
    not has_api_key(),
    reason="ANTHROPIC_API_KEY 환경변수가 필요합니다",
)

# 통합 테스트 마커 (CI에서 스킵하려면 pytest -m "not integration" 사용)
integration_test = pytest.mark.integration


@pytest.fixture(scope="module")
def workspace_path():
    """실제 워크스페이스 경로"""
    return Path(__file__).parent.parent.parent.parent


@pytest.fixture(scope="module")
def ab_logger():
    """A/B 테스트 로거"""
    return ABTestLogger()


@pytest.fixture(scope="module")
def pre_router(workspace_path):
    """PreRouter 인스턴스 (실제 API 사용)"""
    if not has_api_key():
        pytest.skip("ANTHROPIC_API_KEY 필요")

    from anthropic import AsyncAnthropic
    from seosoyoung.routing import PreRouter

    client = AsyncAnthropic()
    return PreRouter(
        workspace_path=workspace_path,
        client=client,
        model="claude-3-5-haiku-latest",
        threshold=5,
        timeout=60.0,  # 도구 수에 따라 충분한 시간 확보
    )


@pytest.mark.integration
class TestRoutingIntegration:
    """라우팅 통합 테스트

    각 테스트는 실제 Haiku API를 호출하여 라우팅 정확도를 검증합니다.
    CI에서 스킵하려면: pytest -m "not integration"
    """

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_lore_character(self, pre_router, ab_logger):
        """캐릭터 정보 요청 → lore 에이전트"""
        request = "펜릭스 성격 알려줘"
        expected_tool = "lore"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="lore_character_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_lore_story(self, pre_router, ab_logger):
        """스토리 관련 요청 → lore 에이전트"""
        request = "액트2 줄거리 요약해줘"
        expected_tool = "lore"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="lore_story_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_ost(self, pre_router, ab_logger):
        """OST 요청 → ost 에이전트"""
        request = "OST 21번 찾아줘"
        expected_tool = "ost"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="ost_search_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_slackbot_dev(self, pre_router, ab_logger):
        """슬랙봇 개발 요청 → slackbot-dev 에이전트"""
        request = "슬랙봇에 새 명령어 추가해줘"
        expected_tool = "slackbot-dev"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="slackbot_dev_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_shay_dev(self, pre_router, ab_logger):
        """섀이 에디터 개발 요청 → shay-dev 에이전트"""
        request = "섀이 에디터 버그 수정해줘"
        expected_tool = "shay-dev"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="shay_dev_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_portal(self, pre_router, ab_logger):
        """포탈 관련 요청 → portal 에이전트"""
        request = "포탈 빌드해줘"
        expected_tool = "portal"
        expected_type = "agent"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="portal_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool == expected_tool,
        )
        ab_logger.log(ab_result)

        assert result.selected_tool == expected_tool, (
            f"Expected {expected_tool}, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_ambiguous_request(self, pre_router, ab_logger):
        """모호한 요청 - 점수 분포 확인"""
        request = "안녕하세요"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="ambiguous_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool="none",  # 모호한 요청은 특정 도구 기대 안 함
            expected_type="none",
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=result.selected_tool is None or result.confidence < 0.7,
        )
        ab_logger.log(ab_result)

        # 모호한 요청은 낮은 신뢰도를 가져야 함
        integration_logger.info(f"Ambiguous request scores: {result.all_scores}")


@pytest.mark.integration
class TestSkillRouting:
    """스킬 라우팅 테스트"""

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_glossary_search(self, pre_router, ab_logger):
        """용어 검색 요청 → lore-search-glossary 스킬"""
        request = "하니엘이 누구야?"
        expected_tool = "lore-search-glossary"
        expected_type = "skill"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="skill_glossary_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=(
                result.selected_tool == expected_tool
                or (result.selected_tool == "lore" and result.tool_type == "agent")
            ),
        )
        ab_logger.log(ab_result)

        # 용어 검색은 스킬 또는 lore 에이전트로 라우팅 가능
        assert result.selected_tool in [expected_tool, "lore"], (
            f"Expected {expected_tool} or lore, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )

    @requires_api_key
    @pytest.mark.asyncio
    async def test_route_dialogue_search(self, pre_router, ab_logger):
        """대사 검색 요청 → lore-search-dialogue 스킬"""
        request = "펜릭스가 루미한테 하는 대사 찾아줘"
        expected_tool = "lore-search-dialogue"
        expected_type = "skill"

        result = await pre_router.route(request)

        ab_result = ABTestResult(
            test_id="skill_dialogue_1",
            timestamp=datetime.now().isoformat(),
            user_request=request,
            expected_tool=expected_tool,
            expected_type=expected_type,
            actual_tool=result.selected_tool,
            actual_type=result.tool_type,
            confidence=result.confidence,
            all_scores=result.all_scores,
            evaluation_time_ms=result.evaluation_time_ms,
            is_correct=(
                result.selected_tool == expected_tool
                or (result.selected_tool == "lore" and result.tool_type == "agent")
            ),
        )
        ab_logger.log(ab_result)

        # 대사 검색은 스킬 또는 lore 에이전트로 라우팅 가능
        assert result.selected_tool in [expected_tool, "lore"], (
            f"Expected {expected_tool} or lore, got {result.selected_tool}. "
            f"Scores: {result.all_scores}"
        )


class TestABTestLogger:
    """A/B 테스트 로거 단위 테스트"""

    def test_log_result(self, tmp_path):
        """로그 기록 테스트"""
        logger = ABTestLogger(log_dir=tmp_path)

        result = ABTestResult(
            test_id="test_1",
            timestamp="2024-01-01T00:00:00",
            user_request="테스트 요청",
            expected_tool="lore",
            expected_type="agent",
            actual_tool="lore",
            actual_type="agent",
            confidence=0.9,
            all_scores={"lore": 9, "ost": 3},
            evaluation_time_ms=150.0,
            is_correct=True,
        )

        logger.log(result)

        # 로그 파일 확인
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1

        with open(log_files[0], encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)
            assert data["test_id"] == "test_1"
            assert data["is_correct"] is True

    def test_summary(self, tmp_path):
        """요약 테스트"""
        logger = ABTestLogger(log_dir=tmp_path)

        # 3개 중 2개 정답
        for i, is_correct in enumerate([True, True, False]):
            result = ABTestResult(
                test_id=f"test_{i}",
                timestamp="2024-01-01T00:00:00",
                user_request="요청",
                expected_tool="lore",
                expected_type="agent",
                actual_tool="lore" if is_correct else "ost",
                actual_type="agent",
                confidence=0.9,
                all_scores={},
                evaluation_time_ms=100.0,
                is_correct=is_correct,
            )
            logger.log(result)

        summary = logger.get_summary()
        assert summary["total"] == 3
        assert summary["correct"] == 2
        assert summary["accuracy"] == pytest.approx(0.667, rel=0.01)


@pytest.mark.integration
class TestRoutingPerformance:
    """라우팅 성능 테스트"""

    @requires_api_key
    @pytest.mark.asyncio
    async def test_routing_time(self, pre_router):
        """라우팅 시간 측정"""
        import time

        requests = [
            "펜릭스 성격 알려줘",
            "OST 목록 보여줘",
            "슬랙봇 버그 수정해",
        ]

        times = []
        for request in requests:
            start = time.perf_counter()
            result = await pre_router.route(request)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            integration_logger.info(
                f"Request: {request[:20]}... → {result.selected_tool} ({elapsed:.1f}ms)"
            )

        avg_time = sum(times) / len(times)
        integration_logger.info(f"Average routing time: {avg_time:.1f}ms")

        # 평균 30초 미만이어야 함 (도구 수가 많을 경우 시간이 더 걸림)
        assert avg_time < 30000, f"Average routing time too slow: {avg_time:.1f}ms"


# pytest 모듈 수준 결과 출력
def pytest_sessionfinish(session, exitstatus):
    """테스트 세션 종료 시 A/B 테스트 요약 출력"""
    pass  # ABTestLogger가 개별적으로 로깅하므로 여기서는 생략
