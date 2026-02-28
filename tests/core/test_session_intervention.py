"""Bot측 session_id 기반 인터벤션 테스트

Phase 3: Bot측 session_id 매핑 및 인터벤션 흐름 검증
1. SoulServiceClient의 session 이벤트 처리
2. ClaudeExecutor의 thread_ts ↔ session_id 매핑
3. 인터벤션 시 session_id 우선 사용 + 폴백
4. session_id 미확보 시 버퍼링 → 확보 후 flush
"""

import asyncio
import json
import threading
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from seosoyoung.slackbot.claude.intervention import InterventionManager, PendingPrompt
from seosoyoung.slackbot.claude.service_client import SoulServiceClient, SSEEvent


# === SoulServiceClient 테스트 ===

class TestServiceClientSessionEvent:
    """SoulServiceClient의 session 이벤트 처리"""

    async def test_session_event_calls_callback(self):
        """SSE session 이벤트 수신 시 on_session 콜백 호출"""
        client = SoulServiceClient(base_url="http://localhost:3105")

        on_session = AsyncMock()
        on_progress = AsyncMock()

        # SSE 이벤트 시뮬레이션
        events = [
            SSEEvent(event="session", data={"session_id": "sess-abc123"}),
            SSEEvent(event="progress", data={"text": "working..."}),
            SSEEvent(event="complete", data={"result": "done", "claude_session_id": "sess-abc123"}),
        ]

        async def mock_parse_stream(response):
            for e in events:
                yield e

        # _parse_sse_stream을 mock
        with patch.object(client, "_parse_sse_stream", mock_parse_stream):
            mock_response = MagicMock()
            result = await client._handle_sse_events(
                response=mock_response,
                on_progress=on_progress,
                on_session=on_session,
            )

        on_session.assert_called_once_with("sess-abc123")
        on_progress.assert_called_once_with("working...")
        assert result.success is True
        assert result.result == "done"

    async def test_session_event_without_callback(self):
        """on_session 콜백 없이도 정상 동작"""
        client = SoulServiceClient(base_url="http://localhost:3105")

        events = [
            SSEEvent(event="session", data={"session_id": "sess-abc123"}),
            SSEEvent(event="complete", data={"result": "done"}),
        ]

        async def mock_parse_stream(response):
            for e in events:
                yield e

        with patch.object(client, "_parse_sse_stream", mock_parse_stream):
            result = await client._handle_sse_events(
                response=MagicMock(),
            )

        assert result.success is True

    async def test_session_event_empty_session_id_ignored(self):
        """빈 session_id는 콜백을 호출하지 않음"""
        client = SoulServiceClient(base_url="http://localhost:3105")
        on_session = AsyncMock()

        events = [
            SSEEvent(event="session", data={"session_id": ""}),
            SSEEvent(event="complete", data={"result": "done"}),
        ]

        async def mock_parse_stream(response):
            for e in events:
                yield e

        with patch.object(client, "_parse_sse_stream", mock_parse_stream):
            await client._handle_sse_events(
                response=MagicMock(),
                on_session=on_session,
            )

        on_session.assert_not_called()


# === ClaudeExecutor session 매핑 테스트 ===

class TestExecutorSessionMapping:
    """ClaudeExecutor의 thread_ts ↔ session_id 매핑"""

    def _make_executor(self, **overrides):
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.claude.session import SessionRuntime
        runtime = MagicMock(spec=SessionRuntime)
        runtime.get_session_lock = overrides.pop("get_session_lock", MagicMock())
        runtime.mark_session_running = overrides.pop("mark_session_running", MagicMock())
        runtime.mark_session_stopped = overrides.pop("mark_session_stopped", MagicMock())
        runtime.get_running_session_count = overrides.pop("get_running_session_count", MagicMock(return_value=1))
        defaults = dict(
            session_manager=MagicMock(),
            session_runtime=runtime,
            restart_manager=MagicMock(is_pending=False),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            update_message_fn=MagicMock(),
        )
        defaults.update(overrides)
        return ClaudeExecutor(**defaults)

    def test_register_and_get_session_id(self):
        """session_id 등록 및 조회"""
        executor = self._make_executor()
        executor._register_session_id("thread_123", "sess-abc")

        assert executor._get_session_id("thread_123") == "sess-abc"

    def test_unregister_session_id(self):
        """session_id 해제"""
        executor = self._make_executor()
        executor._register_session_id("thread_123", "sess-abc")
        executor._unregister_session_id("thread_123")

        assert executor._get_session_id("thread_123") is None

    def test_unregister_nonexistent(self):
        """존재하지 않는 thread_ts 해제 (에러 없음)"""
        executor = self._make_executor()
        executor._unregister_session_id("nonexistent")  # 에러 없이 통과

    def test_pending_buffer_cleared_on_unregister(self):
        """session_id 해제 시 pending 버퍼도 정리"""
        executor = self._make_executor()
        executor._pending_session_interventions["thread_123"] = [("msg", "user")]
        executor._unregister_session_id("thread_123")

        assert "thread_123" not in executor._pending_session_interventions


# === InterventionManager remote 테스트 ===

class TestInterventionRemoteSessionBased:
    """InterventionManager의 session_id 기반 remote 인터벤션"""

    def test_fire_interrupt_remote_with_session_id(self):
        """session_id가 있으면 session 기반 인터벤션 사용"""
        mgr = InterventionManager()
        adapter = MagicMock()
        adapter.intervene_by_session = AsyncMock(return_value=True)

        with patch("seosoyoung.utils.async_bridge.run_in_new_loop") as mock_run:
            mgr.fire_interrupt_remote(
                thread_ts="thread_123",
                prompt="새 질문",
                active_remote_requests={"thread_123": "thread_123"},
                service_adapter=adapter,
                session_id="sess-abc",
            )

        mock_run.assert_called_once()

    def test_fire_interrupt_remote_without_session_id_buffers(self):
        """session_id 미확보 시 버퍼에 보관"""
        mgr = InterventionManager()
        adapter = MagicMock()
        pending = {}
        lock = threading.Lock()

        mgr.fire_interrupt_remote(
            thread_ts="thread_123",
            prompt="새 질문",
            active_remote_requests={"thread_123": "thread_123"},
            service_adapter=adapter,
            session_id=None,
            pending_session_interventions=pending,
            pending_session_lock=lock,
        )

        assert "thread_123" in pending
        assert len(pending["thread_123"]) == 1
        assert pending["thread_123"][0] == ("새 질문", "intervention")

    def test_fire_interrupt_remote_fallback_without_buffer(self):
        """버퍼 없이 session_id도 없으면 기존 폴백"""
        mgr = InterventionManager()
        adapter = MagicMock()
        adapter.intervene = AsyncMock(return_value=True)

        with patch("seosoyoung.utils.async_bridge.run_in_new_loop") as mock_run:
            mgr.fire_interrupt_remote(
                thread_ts="thread_123",
                prompt="새 질문",
                active_remote_requests={"thread_123": "thread_123"},
                service_adapter=adapter,
                session_id=None,
            )

        mock_run.assert_called_once()

    def test_fire_interrupt_remote_no_request_id(self):
        """request_id 없으면 전송 불가"""
        mgr = InterventionManager()
        adapter = MagicMock()

        # 에러 없이 완료
        mgr.fire_interrupt_remote(
            thread_ts="thread_123",
            prompt="새 질문",
            active_remote_requests={},
            service_adapter=adapter,
            session_id=None,
        )


# === 버퍼 flush 테스트 ===

class TestSessionBufferFlush:
    """session_id 확보 시 버퍼된 인터벤션 flush"""

    def test_flush_pending_on_register(self):
        """session_id 등록 시 버퍼된 인터벤션이 flush됨"""
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.claude.session import SessionRuntime

        runtime = MagicMock(spec=SessionRuntime)
        runtime.get_session_lock = MagicMock()
        runtime.mark_session_running = MagicMock()
        runtime.mark_session_stopped = MagicMock()
        runtime.get_running_session_count = MagicMock(return_value=1)

        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            session_runtime=runtime,
            restart_manager=MagicMock(is_pending=False),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            update_message_fn=MagicMock(),
        )

        # 버퍼에 인터벤션 추가
        executor._pending_session_interventions["thread_123"] = [
            ("질문1", "user1"),
            ("질문2", "user2"),
        ]

        # mock adapter 설정
        mock_adapter = MagicMock()
        mock_adapter.intervene_by_session = AsyncMock(return_value=True)
        executor._service_adapter = mock_adapter

        with patch("seosoyoung.slackbot.claude.executor.run_in_new_loop") as mock_run:
            # 원래 run_in_new_loop을 무시 (실행하지 않음)
            mock_run.return_value = True
            executor._register_session_id("thread_123", "sess-abc")

        # flush 후 버퍼 비움
        assert "thread_123" not in executor._pending_session_interventions
        # session_id 매핑 등록됨
        assert executor._get_session_id("thread_123") == "sess-abc"

    def test_no_flush_when_no_pending(self):
        """버퍼가 비어있으면 flush하지 않음"""
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.claude.session import SessionRuntime

        runtime = MagicMock(spec=SessionRuntime)
        runtime.get_session_lock = MagicMock()
        runtime.mark_session_running = MagicMock()
        runtime.mark_session_stopped = MagicMock()
        runtime.get_running_session_count = MagicMock(return_value=1)

        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            session_runtime=runtime,
            restart_manager=MagicMock(is_pending=False),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            update_message_fn=MagicMock(),
        )

        # adapter는 호출되지 않아야 함
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter

        executor._register_session_id("thread_123", "sess-abc")

        # adapter의 어떤 메서드도 호출되지 않음
        mock_adapter.intervene_by_session.assert_not_called()
