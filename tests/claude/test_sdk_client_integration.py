"""ClaudeSDKClient 기반 전환 테스트 (Phase 2)

ClaudeRunner(= ClaudeRunner)가 ClaudeSDKClient를 사용하여:
- 인스턴스별 클라이언트 생명주기 관리
- query + receive_response 기반 실행
- interrupt 동작
을 올바르게 수행하는지 검증합니다.

NOTE: bot-refactor 이후 ClaudeRunner는 thread_ts 단위 인스턴스로 변경되어
_active_clients dict 대신 self.client (단일) 속성을 사용합니다.
"""

import asyncio
import threading
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner


# Mock 메시지 타입
@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockToolUseBlock:
    name: str = "Read"
    input: dict = None


@dataclass
class MockToolResultBlock:
    content: str = "result"


@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockAssistantMessage:
    content: list = None


@dataclass
class MockResultMessage:
    result: str = ""
    session_id: str = None


def _make_mock_client(*messages):
    """mock_receive async generator를 설정한 mock client를 생성하는 헬퍼"""
    mock_client = AsyncMock()

    async def mock_receive():
        for msg in messages:
            yield msg

    # receive_response는 async generator를 반환하는 일반 메서드로 패치
    mock_client.receive_response = mock_receive
    return mock_client


class TestClientLifecycle:
    """인스턴스별 ClaudeSDKClient 생명주기 테스트"""

    def test_client_initially_none(self):
        """생성 직후 client는 None"""
        runner = ClaudeRunner("thread-1")
        assert runner.client is None

    @pytest.mark.asyncio
    async def test_get_or_create_client_creates_new(self):
        """새 클라이언트를 생성하는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            client = await runner._get_or_create_client()

        assert client is mock_client
        mock_client.connect.assert_awaited_once()
        assert runner.client is mock_client

    @pytest.mark.asyncio
    async def test_get_or_create_client_reuses_existing(self):
        """이미 있는 클라이언트를 재사용하는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        runner.client = mock_client

        client = await runner._get_or_create_client()
        assert client is mock_client
        # connect가 다시 호출되지 않아야 함
        mock_client.connect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_remove_client_disconnects_and_clears(self):
        """_remove_client가 disconnect 후 client를 None으로 설정하는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        runner.client = mock_client

        await runner._remove_client()

        mock_client.disconnect.assert_awaited_once()
        assert runner.client is None

    @pytest.mark.asyncio
    async def test_remove_client_when_none_no_error(self):
        """client가 None일 때 _remove_client 호출 시 에러 없이 무시"""
        runner = ClaudeRunner("thread-1")
        await runner._remove_client()
        # 에러 없이 통과

    @pytest.mark.asyncio
    async def test_remove_client_handles_disconnect_error(self):
        """disconnect 실패 시에도 client가 None으로 설정"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        mock_client.disconnect.side_effect = Exception("disconnect error")
        runner.client = mock_client

        await runner._remove_client()
        assert runner.client is None


@pytest.mark.asyncio
class TestRunWithSDKClient:
    """run() 메서드의 ClaudeSDKClient 기반 실행 테스트"""

    async def test_run_uses_sdk_client(self):
        """run()이 ClaudeSDKClient를 사용하는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="sdk-session-1"),
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료됨", session_id="sdk-session-1"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트")

        assert result.success is True
        assert result.output == "완료됨"
        assert result.session_id == "sdk-session-1"
        # query가 호출되었는지 확인
        mock_client.query.assert_awaited_once()

    async def test_run_creates_and_removes_client(self):
        """run() 완료 후 클라이언트가 정리되는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = _make_mock_client(
            MockResultMessage(result="done", session_id="test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        # run 완료 후 클라이언트가 정리되었는지
        mock_client.disconnect.assert_awaited_once()
        assert runner.client is None

    async def test_run_preserves_on_progress_callback(self):
        """run()에서 on_progress 콜백이 동작하는지 확인"""
        runner = ClaudeRunner("thread-1")
        progress_calls = []

        async def on_progress(text):
            progress_calls.append(text)

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="progress-test"),
            MockAssistantMessage(content=[MockTextBlock(text="첫 번째")]),
            MockAssistantMessage(content=[MockTextBlock(text="두 번째")]),
            MockResultMessage(result="완료", session_id="progress-test"),
        )

        time_value = [0]

        def mock_time():
            # 두 번째 호출 시 interval 넘기기
            val = time_value[0]
            time_value[0] += 3
            return val

        mock_loop = MagicMock()
        mock_loop.time = mock_time

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch("asyncio.get_event_loop", return_value=mock_loop):
                                result = await runner.run(
                                    "테스트",
                                    on_progress=on_progress,
                                )

        assert result.success is True

    async def test_run_preserves_om_collection(self):
        """run()에서 OM 대화 수집이 유지되는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="om-test"),
            MockAssistantMessage(content=[MockTextBlock(text="관찰 대상")]),
            MockResultMessage(result="완료", session_id="om-test"),
        )

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.slackbot.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.slackbot.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run("테스트")

        assert result.success is True
        assert len(result.collected_messages) > 0

    async def test_run_handles_connect_error(self):
        """connect() 실패 처리 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        mock_client.connect.side_effect = FileNotFoundError("claude not found")

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            result = await runner.run("테스트")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error


class TestInterrupt:
    """interrupt() 메서드 테스트 (동기)"""

    def test_interrupt_calls_client_interrupt(self):
        """interrupt()가 클라이언트에 interrupt를 호출하는지 확인"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()

        # 실행 중인 이벤트 루프를 시뮬레이션
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        try:
            runner.client = mock_client
            runner.execution_loop = loop

            result = runner.interrupt()
            assert result is True
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)
            runner.client = None
            runner.execution_loop = None

    def test_interrupt_no_client_returns_false(self):
        """클라이언트가 없으면 False 반환"""
        runner = ClaudeRunner("thread-1")

        result = runner.interrupt()
        assert result is False

    def test_interrupt_with_client_returns_true(self):
        """클라이언트가 있으면 True 반환"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        try:
            runner.client = mock_client
            runner.execution_loop = loop

            result = runner.interrupt()
            assert result is True
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)
            runner.client = None
            runner.execution_loop = None

    def test_interrupt_handles_client_error(self):
        """클라이언트 interrupt 실패 시 False 반환"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        mock_client.interrupt.side_effect = Exception("interrupt failed")

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        try:
            runner.client = mock_client
            runner.execution_loop = loop

            result = runner.interrupt()
            assert result is False
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)
            runner.client = None
            runner.execution_loop = None

    def test_interrupt_no_loop_returns_false(self):
        """클라이언트는 있지만 루프가 없으면 False 반환"""
        runner = ClaudeRunner("thread-1")

        mock_client = AsyncMock()
        runner.client = mock_client

        try:
            result = runner.interrupt()
            assert result is False
        finally:
            runner.client = None


@pytest.mark.asyncio
class TestRunWithSessionResume:
    """세션 resume 관련 테스트"""

    async def test_run_with_session_id_sets_resume(self):
        """session_id가 있으면 options.resume에 설정되는지 확인"""
        runner = ClaudeRunner("thread-1")

        captured_options = []
        mock_client = _make_mock_client(
            MockResultMessage(result="done", session_id="resumed"),
        )

        original_build = runner._build_options

        def capture_build(session_id=None, compact_events=None):
            opts = original_build(session_id=session_id, compact_events=compact_events)
            captured_options.append(opts)
            return opts

        with patch("seosoyoung.slackbot.claude.agent_runner.InstrumentedClaudeClient", return_value=mock_client):
            with patch("seosoyoung.slackbot.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", side_effect=capture_build):
                    result = await runner.run(
                        "테스트",
                        session_id="existing-session",
                    )

        assert len(captured_options) > 0
        options, _stderr_file = captured_options[0]
        assert options.resume == "existing-session"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
