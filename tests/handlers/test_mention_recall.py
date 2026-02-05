"""mention 핸들러 Recall 통합 테스트"""

import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from seosoyoung.config import Config


class TestRecallConfig:
    """Recall 설정 테스트

    NOTE: 설정값 파싱 및 기본값 테스트는 test_config.py에서 수행.
    여기서는 Config 클래스에 필요한 속성이 존재하는지만 확인.
    """

    def test_recall_config_attributes_exist(self):
        """Recall 관련 설정 속성 존재 확인"""
        # 클래스 변수로 접근 가능해야 함
        assert hasattr(Config, "RECALL_ENABLED")
        assert hasattr(Config, "RECALL_MODEL")
        assert hasattr(Config, "RECALL_THRESHOLD")
        assert hasattr(Config, "RECALL_TIMEOUT")
        assert hasattr(Config, "RECALL_API_KEY")

    def test_recall_config_types(self):
        """Recall 설정 타입 확인"""
        assert isinstance(Config.RECALL_ENABLED, bool)
        assert isinstance(Config.RECALL_MODEL, str)
        assert isinstance(Config.RECALL_THRESHOLD, int)
        assert isinstance(Config.RECALL_TIMEOUT, float)


class TestMentionHandlerWithRecall:
    """멘션 핸들러 Recall 통합 테스트"""

    @pytest.fixture
    def mock_recall(self):
        """Recall 모킹"""
        from seosoyoung.recall import RecallResult

        mock_result = RecallResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.9,
            summary="캐릭터 정보 요청에 lore 에이전트가 적합합니다.",
            approach="설정 파일에서 정보를 조회합니다.",
            all_scores={"lore": 9, "slackbot-dev": 3},
            evaluation_time_ms=150.0,
            suitable_tools=[
                {"name": "lore", "type": "agent", "score": 9, "reason": "캐릭터 정보", "approach": "설정 파일 조회"}
            ],
        )

        recall = MagicMock()
        recall.analyze = AsyncMock(return_value=mock_result)
        recall.enabled = True
        return recall

    def test_recall_injection_format(self):
        """Recall 결과 프롬프트 주입 형식"""
        from seosoyoung.recall import RecallResult

        result = RecallResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.9,
            summary="캐릭터 정보 요청입니다.",
            approach="설정 파일 조회",
            all_scores={"lore": 9},
            evaluation_time_ms=100.0,
            suitable_tools=[
                {"name": "lore", "type": "agent", "score": 9, "reason": "캐릭터 정보", "approach": "설정 파일 조회"}
            ],
        )

        injection = result.to_prompt_injection()

        # 프롬프트에 필수 정보 포함
        assert "lore" in injection
        assert "agent" in injection.lower() or "에이전트" in injection

    def test_recall_disabled_no_injection(self):
        """Recall 비활성화 시 주입 없음"""
        from seosoyoung.recall import RecallResult

        result = RecallResult(
            selected_tool=None,
            tool_type=None,
            confidence=0.0,
            summary="Recall이 비활성화되어 있습니다.",
            approach="",
            all_scores={},
            evaluation_time_ms=0.0,
        )

        injection = result.to_prompt_injection()

        # 추천이 없으면 빈 문자열
        assert injection == ""


class TestBuildPromptWithRecall:
    """Recall 결과를 포함한 프롬프트 구성 테스트"""

    def test_prompt_includes_recall_result(self):
        """프롬프트에 Recall 결과 포함"""
        from seosoyoung.handlers.mention import build_prompt_with_recall
        from seosoyoung.recall import RecallResult

        recall_result = RecallResult(
            selected_tool="lore",
            tool_type="agent",
            confidence=0.85,
            summary="캐릭터 정보 요청",
            approach="설정 조회",
            all_scores={"lore": 9},
            evaluation_time_ms=100.0,
            suitable_tools=[
                {"name": "lore", "type": "agent", "score": 9, "reason": "캐릭터 정보", "approach": "설정 조회"}
            ],
        )

        prompt = build_prompt_with_recall(
            context="이전 대화...",
            question="펜릭스 성격 알려줘",
            file_context="",
            recall_result=recall_result,
        )

        assert "lore" in prompt
        assert "펜릭스 성격 알려줘" in prompt
        assert "이전 대화..." in prompt

    def test_prompt_without_recall_result(self):
        """Recall 결과 없이 프롬프트 구성"""
        from seosoyoung.handlers.mention import build_prompt_with_recall

        prompt = build_prompt_with_recall(
            context="이전 대화...",
            question="펜릭스 성격 알려줘",
            file_context="",
            recall_result=None,
        )

        # Recall 결과 없어도 기본 프롬프트는 구성됨
        assert "펜릭스 성격 알려줘" in prompt
        assert "이전 대화..." in prompt
