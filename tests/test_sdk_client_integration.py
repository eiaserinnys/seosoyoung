"""ClaudeSDKClient 기반 전환 테스트 (Phase 2)

ClaudeAgentRunner가 ClaudeSDKClient를 사용하여:
- 스레드별 클라이언트 생명주기 관리
- query + receive_response 기반 실행
- interrupt 동작
을 올바르게 수행하는지 검증합니다.
"""

import asyncio
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.claude.agent_runner import ClaudeAgentRunner


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


class TestActiveClientLifecycle:
    """스레드별 ClaudeSDKClient 생명주기 테스트"""

    def setup_method(self):
        ClaudeAgentRunner._reset_shared_loop()

    def test_active_clients_dict_exists(self):
        """_active_clients 딕셔너리가 존재하는지 확인"""
        runner = ClaudeAgentRunner()
        assert hasattr(runner, "_active_clients")
        assert isinstance(runner._active_clients, dict)

    @pytest.mark.asyncio
    async def test_get_or_create_client_creates_new(self):
        """새 스레드에 대해 클라이언트를 생성하는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            client = await runner._get_or_create_client("thread-1")

        assert client is mock_client
        mock_client.connect.assert_awaited_once()
        assert "thread-1" in runner._active_clients

    @pytest.mark.asyncio
    async def test_get_or_create_client_reuses_existing(self):
        """이미 있는 스레드에 대해 기존 클라이언트를 재사용하는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        runner._active_clients["thread-1"] = mock_client

        client = await runner._get_or_create_client("thread-1")
        assert client is mock_client
        # connect가 다시 호출되지 않아야 함
        mock_client.connect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_remove_client_disconnects_and_removes(self):
        """_remove_client가 disconnect 후 딕셔너리에서 제거하는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        runner._active_clients["thread-1"] = mock_client

        await runner._remove_client("thread-1")

        mock_client.disconnect.assert_awaited_once()
        assert "thread-1" not in runner._active_clients

    @pytest.mark.asyncio
    async def test_remove_client_nonexistent_thread_no_error(self):
        """존재하지 않는 스레드 제거 시 에러 없이 무시"""
        runner = ClaudeAgentRunner()
        await runner._remove_client("nonexistent")
        # 에러 없이 통과

    @pytest.mark.asyncio
    async def test_remove_client_handles_disconnect_error(self):
        """disconnect 실패 시에도 딕셔너리에서 제거"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.disconnect.side_effect = Exception("disconnect error")
        runner._active_clients["thread-1"] = mock_client

        await runner._remove_client("thread-1")
        assert "thread-1" not in runner._active_clients


@pytest.mark.asyncio
class TestRunWithSDKClient:
    """run() 메서드의 ClaudeSDKClient 기반 실행 테스트"""

    def setup_method(self):
        ClaudeAgentRunner._reset_shared_loop()

    async def test_run_uses_sdk_client(self):
        """run()이 ClaudeSDKClient를 사용하는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="sdk-session-1"),
            MockAssistantMessage(content=[MockTextBlock(text="진행 중...")]),
            MockResultMessage(result="완료됨", session_id="sdk-session-1"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run(
                                "테스트", thread_ts="thread-1"
                            )

        assert result.success is True
        assert result.output == "완료됨"
        assert result.session_id == "sdk-session-1"
        # query가 호출되었는지 확인
        mock_client.query.assert_awaited_once()

    async def test_run_creates_and_removes_client(self):
        """run() 완료 후 클라이언트가 정리되는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockResultMessage(result="done", session_id="test"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트", thread_ts="thread-1")

        assert result.success is True
        # run 완료 후 클라이언트가 정리되었는지
        mock_client.disconnect.assert_awaited_once()
        assert "thread-1" not in runner._active_clients

    async def test_run_preserves_on_progress_callback(self):
        """run()에서 on_progress 콜백이 동작하는지 확인"""
        runner = ClaudeAgentRunner()
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

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            with patch("asyncio.get_event_loop", return_value=mock_loop):
                                result = await runner.run(
                                    "테스트",
                                    on_progress=on_progress,
                                    thread_ts="thread-1",
                                )

        assert result.success is True

    async def test_run_preserves_om_collection(self):
        """run()에서 OM 대화 수집이 유지되는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = _make_mock_client(
            MockSystemMessage(session_id="om-test"),
            MockAssistantMessage(content=[MockTextBlock(text="관찰 대상")]),
            MockResultMessage(result="완료", session_id="om-test"),
        )

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                with patch("seosoyoung.claude.agent_runner.AssistantMessage", MockAssistantMessage):
                    with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                        with patch("seosoyoung.claude.agent_runner.TextBlock", MockTextBlock):
                            result = await runner.run(
                                "테스트",
                                thread_ts="thread-1",
                                user_id="user-1",
                            )

        assert result.success is True
        assert len(result.collected_messages) > 0

    async def test_run_handles_timeout(self):
        """idle 타임아웃 처리 확인"""
        runner = ClaudeAgentRunner(timeout=1)

        mock_client = AsyncMock()

        async def mock_receive_slow():
            yield MockSystemMessage(session_id="timeout-test")
            await asyncio.sleep(10)
            yield MockResultMessage(result="도달 안 됨")

        mock_client.receive_response = mock_receive_slow

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.SystemMessage", MockSystemMessage):
                result = await runner.run("테스트", thread_ts="thread-1")

        assert result.success is False
        assert "타임아웃" in result.error
        # 타임아웃 후에도 클라이언트 정리
        assert "thread-1" not in runner._active_clients

    async def test_run_handles_connect_error(self):
        """connect() 실패 처리 확인"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.connect.side_effect = FileNotFoundError("claude not found")

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            result = await runner.run("테스트", thread_ts="thread-1")

        assert result.success is False
        assert "찾을 수 없습니다" in result.error


@pytest.mark.asyncio
class TestInterrupt:
    """interrupt() 메서드 테스트"""

    def setup_method(self):
        ClaudeAgentRunner._reset_shared_loop()

    async def test_interrupt_calls_client_interrupt(self):
        """interrupt()가 해당 스레드의 클라이언트에 interrupt를 호출하는지 확인"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        runner._active_clients["thread-1"] = mock_client

        await runner.interrupt("thread-1")
        mock_client.interrupt.assert_awaited_once()

    async def test_interrupt_nonexistent_thread_returns_false(self):
        """존재하지 않는 스레드에 interrupt 시 False 반환"""
        runner = ClaudeAgentRunner()

        result = await runner.interrupt("nonexistent")
        assert result is False

    async def test_interrupt_existing_thread_returns_true(self):
        """존재하는 스레드에 interrupt 시 True 반환"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        runner._active_clients["thread-1"] = mock_client

        result = await runner.interrupt("thread-1")
        assert result is True

    async def test_interrupt_handles_client_error(self):
        """클라이언트 interrupt 실패 시 False 반환"""
        runner = ClaudeAgentRunner()

        mock_client = AsyncMock()
        mock_client.interrupt.side_effect = Exception("interrupt failed")
        runner._active_clients["thread-1"] = mock_client

        result = await runner.interrupt("thread-1")
        assert result is False


@pytest.mark.asyncio
class TestRunWithSessionResume:
    """세션 resume 관련 테스트"""

    def setup_method(self):
        ClaudeAgentRunner._reset_shared_loop()

    async def test_run_with_session_id_sets_resume(self):
        """session_id가 있으면 options.resume에 설정되는지 확인"""
        runner = ClaudeAgentRunner()

        captured_options = []
        mock_client = _make_mock_client(
            MockResultMessage(result="done", session_id="resumed"),
        )

        original_build = runner._build_options

        def capture_build(session_id=None, compact_events=None, user_id=None, thread_ts=None, channel=None):
            opts = original_build(session_id=session_id, compact_events=compact_events, user_id=user_id, thread_ts=thread_ts, channel=channel)
            captured_options.append(opts)
            return opts

        with patch("seosoyoung.claude.agent_runner.ClaudeSDKClient", return_value=mock_client):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                with patch.object(runner, "_build_options", side_effect=capture_build):
                    result = await runner.run(
                        "테스트",
                        session_id="existing-session",
                        thread_ts="thread-1",
                    )

        assert len(captured_options) > 0
        options, _memory_prompt = captured_options[0]
        assert options.resume == "existing-session"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
