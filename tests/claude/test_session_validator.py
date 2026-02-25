"""세션 검증 모듈 테스트

session_validator.py의 validate_session 함수와
ClaudeRunner.run()에서의 세션 사전 검증을 테스트합니다.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from dataclasses import dataclass

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.slackbot.claude.session_validator import (
    validate_session,
    find_session_file,
    SESSION_NOT_FOUND_CODE,
)
from seosoyoung.slackbot.claude.engine_types import EngineResult


# ---------------------------------------------------------------------------
# validate_session 단위 테스트
# ---------------------------------------------------------------------------


class TestValidateSession:
    """validate_session 함수 테스트"""

    def test_invalid_uuid_format(self):
        """잘못된 UUID 형식이면 에러 메시지를 반환"""
        result = validate_session("not-a-uuid")
        assert result is not None
        assert "유효하지 않은 세션 ID 형식" in result

    def test_empty_string(self):
        """빈 문자열이면 에러 메시지를 반환"""
        result = validate_session("")
        assert result is not None
        assert "유효하지 않은 세션 ID 형식" in result

    def test_valid_uuid_no_session_file(self):
        """유효한 UUID지만 세션 파일이 없으면 에러 메시지를 반환"""
        fake_uuid = "12345678-1234-1234-1234-123456789abc"
        with patch(
            "seosoyoung.slackbot.claude.session_validator.find_session_file",
            return_value=None,
        ):
            result = validate_session(fake_uuid)
            assert result is not None
            assert "세션을 찾을 수 없습니다" in result

    def test_valid_uuid_with_session_file(self):
        """유효한 UUID이고 세션 파일이 있으면 None을 반환 (성공)"""
        fake_uuid = "12345678-1234-1234-1234-123456789abc"
        fake_path = Path("/tmp/fake_session.jsonl")
        with patch(
            "seosoyoung.slackbot.claude.session_validator.find_session_file",
            return_value=fake_path,
        ):
            result = validate_session(fake_uuid)
            assert result is None


class TestFindSessionFile:
    """find_session_file 함수 테스트"""

    def test_no_claude_dir(self, tmp_path):
        """~/.claude/projects 디렉토리가 없으면 None 반환"""
        with patch("seosoyoung.slackbot.claude.session_validator.Path.home", return_value=tmp_path):
            result = find_session_file("12345678-1234-1234-1234-123456789abc")
            assert result is None

    def test_session_file_found(self, tmp_path):
        """세션 파일이 있으면 경로를 반환"""
        session_id = "12345678-1234-1234-1234-123456789abc"
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)
        session_file = projects_dir / f"{session_id}.jsonl"
        session_file.write_text("{}")

        with patch("seosoyoung.slackbot.claude.session_validator.Path.home", return_value=tmp_path):
            result = find_session_file(session_id)
            assert result is not None
            assert result.name == f"{session_id}.jsonl"

    def test_session_file_not_found(self, tmp_path):
        """세션 파일이 없으면 None 반환"""
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        with patch("seosoyoung.slackbot.claude.session_validator.Path.home", return_value=tmp_path):
            result = find_session_file("nonexistent-1234-1234-1234-123456789abc")
            assert result is None


# ---------------------------------------------------------------------------
# ClaudeRunner.run() 세션 검증 통합 테스트
# ---------------------------------------------------------------------------


@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list = None


@dataclass
class MockResultMessage:
    result: str = ""
    session_id: str = None
    is_error: bool = False


def _make_mock_client(*messages):
    """mock client를 생성하는 헬퍼"""
    mock_client = AsyncMock()

    async def mock_receive():
        for msg in messages:
            yield msg

    mock_client.receive_response = mock_receive
    return mock_client


class TestRunnerSessionValidation:
    """ClaudeRunner.run()의 세션 검증 테스트"""

    @pytest.mark.asyncio
    async def test_invalid_session_returns_error(self):
        """존재하지 않는 세션 ID -> EngineResult.error로 즉시 실패"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner(thread_ts="test.123")
        fake_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        with patch(
            "seosoyoung.slackbot.claude.agent_runner.validate_session",
            return_value="세션을 찾을 수 없습니다: " + fake_uuid,
        ):
            result = await runner.run("test prompt", session_id=fake_uuid)

        assert isinstance(result, EngineResult)
        assert result.success is False
        assert result.error is not None
        assert "세션을 찾을 수 없습니다" in result.error
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_valid_session_proceeds_to_execute(self):
        """존재하는 세션 ID -> 정상 실행 (검증 통과 후 _execute 호출)"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner(thread_ts="test.456")
        fake_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        expected_result = EngineResult(
            success=True,
            output="테스트 응답",
            session_id=fake_uuid,
        )

        with patch(
            "seosoyoung.slackbot.claude.agent_runner.validate_session",
            return_value=None,  # 검증 성공
        ), patch.object(
            runner,
            "_execute",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_execute:
            result = await runner.run("test prompt", session_id=fake_uuid)

        assert result.success is True
        assert result.output == "테스트 응답"
        assert result.session_id == fake_uuid
        mock_execute.assert_called_once_with(
            "test prompt", fake_uuid, None, None, None
        )

    @pytest.mark.asyncio
    async def test_no_session_id_skips_validation(self):
        """session_id가 None이면 검증 건너뛰고 바로 실행"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner(thread_ts="test.789")

        expected_result = EngineResult(
            success=True,
            output="새 세션 응답",
        )

        with patch(
            "seosoyoung.slackbot.claude.agent_runner.validate_session",
        ) as mock_validate, patch.object(
            runner,
            "_execute",
            new_callable=AsyncMock,
            return_value=expected_result,
        ):
            result = await runner.run("test prompt")

        assert result.success is True
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_returns_error(self):
        """잘못된 형식의 세션 ID -> 즉시 실패"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner

        runner = ClaudeRunner(thread_ts="test.format")
        bad_session_id = "not-valid-uuid"

        with patch(
            "seosoyoung.slackbot.claude.agent_runner.validate_session",
            return_value=f"유효하지 않은 세션 ID 형식입니다: {bad_session_id}",
        ):
            result = await runner.run("test prompt", session_id=bad_session_id)

        assert result.success is False
        assert "유효하지 않은 세션 ID 형식" in result.error


# ---------------------------------------------------------------------------
# soul 하위호환 re-export 테스트
# ---------------------------------------------------------------------------
# TestSoulReExport: 삭제됨 (soul/service/session_validator.py re-export shim 제거)
# soul은 이제 slackbot.claude.session_validator를 직접 사용합니다.
