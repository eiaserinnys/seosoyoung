"""ClaudeServiceAdapter 테스트

SoulServiceClient를 mock하여 adapter의 ClaudeResult 변환을 검증합니다.
per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import pytest
from unittest.mock import AsyncMock

from seosoyoung.slackbot.soulstream.engine_types import ClaudeResult
from seosoyoung.slackbot.soulstream.service_adapter import ClaudeServiceAdapter
from seosoyoung.slackbot.soulstream.service_client import (
    SoulServiceClient,
    SoulServiceError,
    SessionConflictError,
    SessionNotFoundError,
    SessionNotRunningError,
    RateLimitError,
    ExecuteResult,
)


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=SoulServiceClient)
    client.is_configured = True
    return client


@pytest.fixture
def adapter(mock_client):
    from seosoyoung.slackbot.marker_parser import parse_markers
    return ClaudeServiceAdapter(client=mock_client, parse_markers_fn=parse_markers)


class TestExecute:
    """ClaudeServiceAdapter.execute() 테스트"""

    @pytest.mark.asyncio
    async def test_success_returns_agent_session_id(self, adapter, mock_client):
        """성공 시 ClaudeResult.session_id에 agent_session_id가 저장되어야 한다.

        resume/intervention 시 soulstream이 agent_session_id로 세션을 조회하므로,
        claude_session_id가 아닌 agent_session_id를 반환해야 한다.
        """
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="안녕하세요",
            agent_session_id="sess-abc-123",
            claude_session_id="ff1c7cfa-xxxx",
        )

        result = await adapter.execute(prompt="hello")

        assert isinstance(result, ClaudeResult)
        assert result.success is True
        assert result.output == "안녕하세요"
        # 핵심: session_id는 agent_session_id여야 한다
        assert result.session_id == "sess-abc-123"

    @pytest.mark.asyncio
    async def test_session_id_is_not_claude_session_id(self, adapter, mock_client):
        """ClaudeResult.session_id가 claude_session_id가 아닌지 명시적으로 검증"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="done",
            agent_session_id="sess-agent-001",
            claude_session_id="claude-internal-uuid",
        )

        result = await adapter.execute(prompt="test")

        assert result.session_id != "claude-internal-uuid"
        assert result.session_id == "sess-agent-001"

    @pytest.mark.asyncio
    async def test_resume_with_agent_session_id(self, adapter, mock_client):
        """agent_session_id를 전달하면 resume으로 동작"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="resumed",
            agent_session_id="sess-abc-123",
        )

        await adapter.execute(
            prompt="follow-up",
            agent_session_id="sess-abc-123",
        )

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["agent_session_id"] == "sess-abc-123"

    @pytest.mark.asyncio
    async def test_success_with_update_marker(self, adapter, mock_client):
        """<!-- UPDATE --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="코드 변경 완료.\n<!-- UPDATE -->",
            agent_session_id="sess-456",
        )

        result = await adapter.execute(prompt="update code")

        assert result.success is True
        assert result.update_requested is True
        assert result.restart_requested is False

    @pytest.mark.asyncio
    async def test_success_with_restart_marker(self, adapter, mock_client):
        """<!-- RESTART --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="재시작 필요.\n<!-- RESTART -->",
            agent_session_id="sess-789",
        )

        result = await adapter.execute(prompt="restart")

        assert result.success is True
        assert result.restart_requested is True

    @pytest.mark.asyncio
    async def test_success_with_list_run_marker(self, adapter, mock_client):
        """<!-- LIST_RUN: xxx --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="정주행 시작.\n<!-- LIST_RUN: 📌 PLAN: 테스트 -->",
            agent_session_id="sess-101",
        )

        result = await adapter.execute(prompt="list run")

        assert result.success is True
        assert result.list_run == "📌 PLAN: 테스트"

    @pytest.mark.asyncio
    async def test_failure(self, adapter, mock_client):
        """실패 시 ClaudeResult.success=False"""
        mock_client.execute.return_value = ExecuteResult(
            success=False,
            result="연결 타임아웃",
            error="연결 타임아웃",
        )

        result = await adapter.execute(prompt="hello")

        assert result.success is False
        assert result.error == "연결 타임아웃"

    @pytest.mark.asyncio
    async def test_conflict_error(self, adapter, mock_client):
        """SessionConflictError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = SessionConflictError("conflict")

        result = await adapter.execute(prompt="hello")

        assert result.success is False
        assert "이미 실행 중" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, adapter, mock_client):
        """RateLimitError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = RateLimitError("rate limit")

        result = await adapter.execute(prompt="hello")

        assert result.success is False
        assert "동시 실행 제한" in result.error

    @pytest.mark.asyncio
    async def test_service_error(self, adapter, mock_client):
        """SoulServiceError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = SoulServiceError("network error")

        result = await adapter.execute(prompt="hello")

        assert result.success is False
        assert "Soulstream 오류" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_error(self, adapter, mock_client):
        """예상치 못한 예외 → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = RuntimeError("unexpected")

        result = await adapter.execute(prompt="hello")

        assert result.success is False
        assert "원격 실행 오류" in result.error

    @pytest.mark.asyncio
    async def test_progress_callback_forwarded(self, adapter, mock_client):
        """on_progress 콜백이 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")

        on_progress = AsyncMock()
        await adapter.execute(prompt="hello", on_progress=on_progress)

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["on_progress"] is on_progress

    @pytest.mark.asyncio
    async def test_tool_settings_forwarded(self, adapter, mock_client):
        """allowed_tools/disallowed_tools/use_mcp가 SoulServiceClient에 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")

        await adapter.execute(
            prompt="hello",
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"],
            use_mcp=False,
        )

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["allowed_tools"] == ["Read", "Glob"]
        assert call_kwargs["disallowed_tools"] == ["Bash"]
        assert call_kwargs["use_mcp"] is False

    @pytest.mark.asyncio
    async def test_tool_settings_defaults(self, adapter, mock_client):
        """도구 설정 미지정 시 기본값이 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")

        await adapter.execute(prompt="hello")

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs.get("allowed_tools") is None
        assert call_kwargs.get("disallowed_tools") is None
        assert call_kwargs.get("use_mcp") is True

    @pytest.mark.asyncio
    async def test_on_debug_callback_forwarded(self, adapter, mock_client):
        """on_debug 콜백이 SoulServiceClient에 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")

        on_debug = AsyncMock()
        await adapter.execute(prompt="hello", on_debug=on_debug)

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["on_debug"] is on_debug

    @pytest.mark.asyncio
    async def test_on_session_callback_forwarded(self, adapter, mock_client):
        """on_session 콜백이 SoulServiceClient에 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")

        on_session = AsyncMock()
        await adapter.execute(prompt="hello", on_session=on_session)

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["on_session"] is on_session


class TestIntervene:
    """ClaudeServiceAdapter.intervene() 테스트"""

    @pytest.mark.asyncio
    async def test_intervene_success(self, adapter, mock_client):
        mock_client.intervene.return_value = {"queued": True}

        result = await adapter.intervene(
            agent_session_id="sess-abc",
            text="추가 지시",
            user="user1",
        )
        assert result is True
        mock_client.intervene.assert_awaited_once_with(
            agent_session_id="sess-abc",
            text="추가 지시",
            user="user1",
            attachment_paths=None,
        )

    @pytest.mark.asyncio
    async def test_intervene_not_found(self, adapter, mock_client):
        mock_client.intervene.side_effect = SessionNotFoundError("not found")

        result = await adapter.intervene(
            agent_session_id="sess-abc",
            text="hello",
            user="user1",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_intervene_not_running(self, adapter, mock_client):
        mock_client.intervene.side_effect = SessionNotRunningError("not running")

        result = await adapter.intervene(
            agent_session_id="sess-abc",
            text="hello",
            user="user1",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_intervene_unexpected_error(self, adapter, mock_client):
        mock_client.intervene.side_effect = RuntimeError("unexpected")

        result = await adapter.intervene(
            agent_session_id="sess-abc",
            text="hello",
            user="user1",
        )
        assert result is False


class TestClose:
    """ClaudeServiceAdapter.close() 테스트"""

    @pytest.mark.asyncio
    async def test_close(self, adapter, mock_client):
        await adapter.close()
        mock_client.close.assert_awaited_once()
