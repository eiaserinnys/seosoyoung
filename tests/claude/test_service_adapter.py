"""ClaudeServiceAdapter 테스트

SoulServiceClient를 mock하여 adapter의 ClaudeResult 변환을 검증합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
from seosoyoung.slackbot.claude.service_adapter import ClaudeServiceAdapter
from seosoyoung.slackbot.claude.service_client import (
    SoulServiceClient,
    SoulServiceError,
    TaskConflictError,
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
    return ClaudeServiceAdapter(client=mock_client, client_id="test_bot",
                                parse_markers_fn=parse_markers)


class TestExecute:
    """ClaudeServiceAdapter.execute() 테스트"""

    @pytest.mark.asyncio
    async def test_success(self, adapter, mock_client):
        """성공 시 ClaudeResult.success=True"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="안녕하세요",
            claude_session_id="sess-123",
        )
        mock_client.ack.return_value = True

        result = await adapter.execute(
            prompt="hello",
            request_id="thread-1",
        )

        assert isinstance(result, ClaudeResult)
        assert result.success is True
        assert result.output == "안녕하세요"
        assert result.session_id == "sess-123"
        mock_client.ack.assert_awaited_once_with("test_bot", "thread-1")

    @pytest.mark.asyncio
    async def test_success_with_update_marker(self, adapter, mock_client):
        """<!-- UPDATE --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="코드 변경 완료.\n<!-- UPDATE -->",
            claude_session_id="sess-456",
        )
        mock_client.ack.return_value = True

        result = await adapter.execute(prompt="update code", request_id="thread-2")

        assert result.success is True
        assert result.update_requested is True
        assert result.restart_requested is False

    @pytest.mark.asyncio
    async def test_success_with_restart_marker(self, adapter, mock_client):
        """<!-- RESTART --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="재시작 필요.\n<!-- RESTART -->",
        )
        mock_client.ack.return_value = True

        result = await adapter.execute(prompt="restart", request_id="thread-3")

        assert result.success is True
        assert result.restart_requested is True

    @pytest.mark.asyncio
    async def test_success_with_list_run_marker(self, adapter, mock_client):
        """<!-- LIST_RUN: xxx --> 마커 추출"""
        mock_client.execute.return_value = ExecuteResult(
            success=True,
            result="정주행 시작.\n<!-- LIST_RUN: 📌 PLAN: 테스트 -->",
        )
        mock_client.ack.return_value = True

        result = await adapter.execute(prompt="list run", request_id="thread-4")

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

        result = await adapter.execute(prompt="hello", request_id="thread-5")

        assert result.success is False
        assert result.error == "연결 타임아웃"
        mock_client.ack.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_conflict_error(self, adapter, mock_client):
        """TaskConflictError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = TaskConflictError("conflict")

        result = await adapter.execute(prompt="hello", request_id="thread-6")

        assert result.success is False
        assert "이미 실행 중" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, adapter, mock_client):
        """RateLimitError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = RateLimitError("rate limit")

        result = await adapter.execute(prompt="hello", request_id="thread-7")

        assert result.success is False
        assert "동시 실행 제한" in result.error

    @pytest.mark.asyncio
    async def test_service_error(self, adapter, mock_client):
        """SoulServiceError → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = SoulServiceError("network error")

        result = await adapter.execute(prompt="hello", request_id="thread-8")

        assert result.success is False
        assert "소울 서비스 오류" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_error(self, adapter, mock_client):
        """예상치 못한 예외 → ClaudeResult(success=False)"""
        mock_client.execute.side_effect = RuntimeError("unexpected")

        result = await adapter.execute(prompt="hello", request_id="thread-9")

        assert result.success is False
        assert "원격 실행 오류" in result.error

    @pytest.mark.asyncio
    async def test_progress_callback_forwarded(self, adapter, mock_client):
        """on_progress 콜백이 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")
        mock_client.ack.return_value = True

        on_progress = AsyncMock()
        await adapter.execute(
            prompt="hello",
            request_id="thread-10",
            on_progress=on_progress,
        )

        # execute에 on_progress가 전달되었는지 확인
        call_kwargs = mock_client.execute.call_args.kwargs
        assert "on_progress" in call_kwargs
        assert call_kwargs["on_progress"] is on_progress

    @pytest.mark.asyncio
    async def test_resume_session_id_forwarded(self, adapter, mock_client):
        """resume_session_id가 전달되는지 확인"""
        mock_client.execute.return_value = ExecuteResult(success=True, result="done")
        mock_client.ack.return_value = True

        await adapter.execute(
            prompt="hello",
            request_id="thread-11",
            resume_session_id="prev-sess",
        )

        call_kwargs = mock_client.execute.call_args.kwargs
        assert call_kwargs["resume_session_id"] == "prev-sess"


class TestIntervene:
    """ClaudeServiceAdapter.intervene() 테스트"""

    @pytest.mark.asyncio
    async def test_intervene_success(self, adapter, mock_client):
        mock_client.intervene.return_value = {"queued": True}

        result = await adapter.intervene("thread-1", "추가 지시", "user1")
        assert result is True
        mock_client.intervene.assert_awaited_once_with(
            client_id="test_bot",
            request_id="thread-1",
            text="추가 지시",
            user="user1",
        )

    @pytest.mark.asyncio
    async def test_intervene_not_found(self, adapter, mock_client):
        from seosoyoung.slackbot.claude.service_client import TaskNotFoundError
        mock_client.intervene.side_effect = TaskNotFoundError("not found")

        result = await adapter.intervene("thread-1", "hello", "user1")
        assert result is False

    @pytest.mark.asyncio
    async def test_intervene_unexpected_error(self, adapter, mock_client):
        mock_client.intervene.side_effect = RuntimeError("unexpected")

        result = await adapter.intervene("thread-1", "hello", "user1")
        assert result is False


class TestClose:
    """ClaudeServiceAdapter.close() 테스트"""

    @pytest.mark.asyncio
    async def test_close(self, adapter, mock_client):
        await adapter.close()
        mock_client.close.assert_awaited_once()
