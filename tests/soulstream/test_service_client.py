"""SoulServiceClient 테스트

mock aiohttp 서버를 사용하여 HTTP + SSE 클라이언트 동작을 검증합니다.
per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from seosoyoung.slackbot.soulstream.service_client import (
    SoulServiceClient,
    SoulServiceError,
    SessionConflictError,
    SessionNotFoundError,
    SessionNotRunningError,
    RateLimitError,
    ConnectionLostError,
    ExponentialBackoff,
    ExecuteResult,
    SSEEvent,
    SSE_PERSIST_RECONNECT_DELAY,
    # 하위 호환 별칭
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
)


# === 헬퍼 ===

class MockAsyncContextManager:
    """aiohttp의 async with session.post() 패턴을 mock하기 위한 컨텍스트 매니저"""
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _mock_session(response, method="post"):
    """mock aiohttp 세션 생성"""
    session = MagicMock()
    session.closed = False
    ctx = MockAsyncContextManager(response)
    getattr(session, method).return_value = ctx
    return session


def _make_stream_reader(data: bytes):
    """바이트 데이터를 readline()으로 읽을 수 있는 mock 스트림 리더 생성"""
    lines = []
    remaining = data
    while remaining:
        idx = remaining.find(b"\n")
        if idx >= 0:
            lines.append(remaining[: idx + 1])
            remaining = remaining[idx + 1 :]
        else:
            lines.append(remaining)
            remaining = b""
    lines.append(b"")  # EOF

    reader = AsyncMock()
    reader.readline = AsyncMock(side_effect=lines)
    return reader


class TestExponentialBackoff:
    """ExponentialBackoff 유틸리티 테스트"""

    def test_initial_state(self):
        backoff = ExponentialBackoff()
        assert backoff.attempt == 0
        assert backoff.should_retry()

    def test_delay_increases(self):
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=16.0)
        delays = []
        for _ in range(5):
            delays.append(backoff.get_delay())
            backoff.increment()
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_max_delay_cap(self):
        backoff = ExponentialBackoff(base_delay=1.0, max_delay=4.0)
        backoff.attempt = 10
        assert backoff.get_delay() == 4.0

    def test_should_retry_limit(self):
        backoff = ExponentialBackoff(max_retries=3)
        for _ in range(3):
            assert backoff.should_retry()
            backoff.increment()
        assert not backoff.should_retry()

    def test_reset(self):
        backoff = ExponentialBackoff()
        backoff.attempt = 5
        backoff.reset()
        assert backoff.attempt == 0
        assert backoff.should_retry()


class TestSoulServiceClient:
    """SoulServiceClient 테스트"""

    def test_is_configured(self):
        client = SoulServiceClient(base_url="http://localhost:3105")
        assert client.is_configured

    def test_is_not_configured_empty(self):
        client = SoulServiceClient(base_url="")
        assert not client.is_configured

    def test_build_headers_with_token(self):
        client = SoulServiceClient(base_url="http://localhost:3105", token="test-token")
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_without_token(self):
        client = SoulServiceClient(base_url="http://localhost:3105")
        headers = client._build_headers()
        assert "Authorization" not in headers

    def test_backward_compat_aliases(self):
        """하위 호환 별칭이 올바르게 매핑되는지 확인"""
        assert TaskConflictError is SessionConflictError
        assert TaskNotFoundError is SessionNotFoundError
        assert TaskNotRunningError is SessionNotRunningError


class TestSoulServiceClientExecute:
    """SoulServiceClient.execute() 테스트 (per-session, mock aiohttp)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_execute_conflict_raises(self, client):
        """409 응답 시 SessionConflictError"""
        mock_response = MagicMock()
        mock_response.status = 409
        client._session = _mock_session(mock_response)

        with pytest.raises(SessionConflictError):
            await client.execute("hello")

    @pytest.mark.asyncio
    async def test_execute_rate_limit_raises(self, client):
        """503 응답 시 RateLimitError"""
        mock_response = MagicMock()
        mock_response.status = 503
        client._session = _mock_session(mock_response)

        with pytest.raises(RateLimitError):
            await client.execute("hello")

    @pytest.mark.asyncio
    async def test_execute_generic_error_raises(self, client):
        """기타 에러 상태 코드 시 SoulServiceError"""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": {"message": "internal error"}})
        client._session = _mock_session(mock_response)

        with pytest.raises(SoulServiceError, match="internal error"):
            await client.execute("hello")

    @pytest.mark.asyncio
    async def test_execute_sends_prompt_only(self, client):
        """기본 execute: prompt만 전송, agent_session_id 없음"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"new-sess-1"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done","claude_session_id":"sess-1"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)

        session = _mock_session(mock_response)
        client._session = session

        result = await client.execute("hello")

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["prompt"] == "hello"
        assert "agent_session_id" not in body
        assert result.agent_session_id == "new-sess-1"

    @pytest.mark.asyncio
    async def test_execute_with_agent_session_id(self, client):
        """resume: agent_session_id 포함하여 전송"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"existing-sess"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"resumed"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)

        session = _mock_session(mock_response)
        client._session = session

        result = await client.execute("continue", agent_session_id="existing-sess")

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["agent_session_id"] == "existing-sess"

    @pytest.mark.asyncio
    async def test_execute_includes_tool_settings_in_body(self, client):
        """allowed_tools/disallowed_tools/use_mcp가 HTTP body에 포함되는지 확인"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-tools"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done","claude_session_id":"sess-1"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)

        session = _mock_session(mock_response)
        client._session = session

        await client.execute(
            "hello",
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"],
            use_mcp=False,
        )

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["allowed_tools"] == ["Read", "Glob"]
        assert body["disallowed_tools"] == ["Bash"]
        assert body["use_mcp"] is False

    @pytest.mark.asyncio
    async def test_execute_omits_none_tools_from_body(self, client):
        """allowed_tools/disallowed_tools가 None이면 body에서 생략"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-no-tools"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)

        session = _mock_session(mock_response)
        client._session = session

        await client.execute("hello")

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "allowed_tools" not in body
        assert "disallowed_tools" not in body
        assert body["use_mcp"] is True  # 기본값

    @pytest.mark.asyncio
    async def test_execute_init_event_triggers_on_session(self, client):
        """init 이벤트가 on_session 콜백을 호출하는지 확인"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"new-sess-cb"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)
        client._session = _mock_session(mock_response)

        session_ids = []

        async def on_session(sid):
            session_ids.append(sid)

        result = await client.execute("hello", on_session=on_session)
        assert session_ids == ["new-sess-cb"]
        assert result.agent_session_id == "new-sess-cb"


class TestSoulServiceClientIntervene:
    """SoulServiceClient.intervene() 테스트 (per-session)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_intervene_success(self, client):
        """202 응답 시 성공"""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.json = AsyncMock(return_value={"queued": True, "queue_position": 1})
        client._session = _mock_session(mock_response)

        result = await client.intervene("sess-123", "추가 지시", "user1")
        assert result["queued"] is True

    @pytest.mark.asyncio
    async def test_intervene_with_attachments(self, client):
        """attachment_paths 포함 전송"""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.json = AsyncMock(return_value={"queued": True})
        session = _mock_session(mock_response)
        client._session = session

        await client.intervene(
            "sess-123", "look at this", "user1",
            attachment_paths=["/path/to/file.png"],
        )

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["attachment_paths"] == ["/path/to/file.png"]

    @pytest.mark.asyncio
    async def test_intervene_not_found(self, client):
        """404 응답 시 SessionNotFoundError"""
        mock_response = MagicMock()
        mock_response.status = 404
        client._session = _mock_session(mock_response)

        with pytest.raises(SessionNotFoundError):
            await client.intervene("sess-missing", "hello", "user1")

    @pytest.mark.asyncio
    async def test_intervene_not_running(self, client):
        """409 응답 시 SessionNotRunningError"""
        mock_response = MagicMock()
        mock_response.status = 409
        client._session = _mock_session(mock_response)

        with pytest.raises(SessionNotRunningError):
            await client.intervene("sess-done", "hello", "user1")

    @pytest.mark.asyncio
    async def test_intervene_url(self, client):
        """intervene가 올바른 URL을 호출하는지 확인"""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.json = AsyncMock(return_value={"queued": True})
        session = _mock_session(mock_response)
        client._session = session

        await client.intervene("sess-abc", "hello", "user1")

        call_args = session.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert url == "http://localhost:3105/sessions/sess-abc/intervene"


class TestSoulServiceClientReconnect:
    """SoulServiceClient.reconnect_stream() 테스트 (per-session)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_reconnect_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status = 404
        client._session = _mock_session(mock_response, method="get")

        with pytest.raises(SessionNotFoundError):
            await client.reconnect_stream("sess-missing")

    @pytest.mark.asyncio
    async def test_reconnect_success(self, client):
        """재연결 + complete 이벤트"""
        sse_data = (
            b"event:complete\n"
            b'data:{"type":"complete","result":"reconnect done","claude_session_id":"sess-r"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)
        client._session = _mock_session(mock_response, method="get")

        result = await client.reconnect_stream("sess-123")
        assert result.success is True
        assert result.result == "reconnect done"

    @pytest.mark.asyncio
    async def test_reconnect_url(self, client):
        """reconnect_stream이 올바른 URL을 호출하는지 확인"""
        sse_data = (
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)
        session = _mock_session(mock_response, method="get")
        client._session = session

        await client.reconnect_stream("sess-xyz")

        call_args = session.get.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert url == "http://localhost:3105/events/sess-xyz/stream"


class TestHandleSSEEvents:
    """_handle_sse_events 테스트 (SSE 스트림 처리)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105")

    @pytest.mark.asyncio
    async def test_init_event(self, client):
        """init 이벤트에서 agent_session_id를 읽는다"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-init-123"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        session_ids = []
        async def on_session(sid):
            session_ids.append(sid)

        result = await client._handle_sse_events(mock_response, on_session=on_session)
        assert result.success is True
        assert result.agent_session_id == "sess-init-123"
        assert session_ids == ["sess-init-123"]

    @pytest.mark.asyncio
    async def test_complete_event(self, client):
        """complete 이벤트로 성공 결과 반환"""
        sse_data = (
            b"event:complete\n"
            b'data:{"type":"complete","result":"hello world","claude_session_id":"sess-123"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        result = await client._handle_sse_events(mock_response)
        assert result.success is True
        assert result.result == "hello world"
        assert result.claude_session_id == "sess-123"

    @pytest.mark.asyncio
    async def test_error_event(self, client):
        """error 이벤트로 실패 결과 반환"""
        sse_data = (
            b"event:error\n"
            b'data:{"type":"error","message":"something went wrong"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        result = await client._handle_sse_events(mock_response)
        assert result.success is False
        assert "something went wrong" in result.result

    @pytest.mark.asyncio
    async def test_compact_callback(self, client):
        """compact 이벤트가 콜백을 호출하는지 확인"""
        sse_data = (
            b"event:compact\n"
            b'data:{"type":"compact","trigger":"auto","message":"compacted"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        compact_events = []

        async def on_compact(trigger, message):
            compact_events.append((trigger, message))

        result = await client._handle_sse_events(mock_response, on_compact=on_compact)
        assert result.success is True
        assert len(compact_events) == 1
        assert compact_events[0] == ("auto", "compacted")

    @pytest.mark.asyncio
    async def test_debug_callback(self, client):
        """debug 이벤트가 on_debug 콜백을 호출하는지 확인"""
        sse_data = (
            b"event:debug\n"
            b'data:{"type":"debug","message":"rate limit warning: 80% used"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        debug_messages = []

        async def on_debug(message):
            debug_messages.append(message)

        result = await client._handle_sse_events(mock_response, on_debug=on_debug)
        assert result.success is True
        assert len(debug_messages) == 1
        assert "rate limit warning" in debug_messages[0]

    @pytest.mark.asyncio
    async def test_debug_callback_not_called_without_handler(self, client):
        """on_debug가 None이어도 에러 없이 처리"""
        sse_data = (
            b"event:debug\n"
            b'data:{"type":"debug","message":"some debug info"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        # on_debug=None (기본값)으로 호출 -- 에러 없어야 함
        result = await client._handle_sse_events(mock_response)
        assert result.success is True
        assert result.result == "done"

    @pytest.mark.asyncio
    async def test_debug_empty_message_ignored(self, client):
        """빈 debug 메시지는 콜백을 호출하지 않음"""
        sse_data = (
            b"event:debug\n"
            b'data:{"type":"debug","message":""}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        debug_messages = []

        async def on_debug(message):
            debug_messages.append(message)

        result = await client._handle_sse_events(mock_response, on_debug=on_debug)
        assert result.success is True
        assert len(debug_messages) == 0  # 빈 메시지는 무시

    @pytest.mark.asyncio
    async def test_keepalive_ignored(self, client):
        """SSE 코멘트(keepalive)가 무시되는지 확인"""
        sse_data = (
            b": keepalive\n"
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"after keepalive"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        result = await client._handle_sse_events(mock_response)
        assert result.success is True
        assert result.result == "after keepalive"

    @pytest.mark.asyncio
    async def test_sse_event_id_parsed(self, client):
        """SSE id: 필드가 SSEEvent.id에 파싱되는지 확인"""
        sse_data = (
            b"event:progress\n"
            b"id:evt-42\n"
            b'data:{"text":"step 1"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        events = []
        async for event in client._parse_sse_stream(mock_response):
            events.append(event)

        assert len(events) == 2
        assert events[0].id == "evt-42"
        assert events[1].id is None  # complete에는 id 없음


class TestSSEReconnection:
    """SSE 연결 끊김 시 자동 재연결 테스트 (per-session)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_connection_lost_triggers_reconnect(self, client):
        """연결 끊김 시 reconnect_stream()으로 재연결하여 결과를 받는다"""
        import aiohttp

        # 첫 번째 응답: init 이벤트 후 연결 끊김
        # init 이벤트를 먼저 보내고 그 다음 끊기도록 구성
        init_line = b"event:init\n"
        init_data = b'data:{"agent_session_id":"sess-recon"}\n'
        init_end = b"\n"

        lines = [init_line, init_data, init_end]
        # 이후 ClientPayloadError 발생
        reader = AsyncMock()
        call_count = 0
        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(lines):
                result = lines[call_count]
                call_count += 1
                return result
            raise aiohttp.ClientPayloadError("Connection lost")
        reader.readline = AsyncMock(side_effect=readline_side_effect)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = reader
        client._session = _mock_session(mock_response)

        # reconnect_stream mock: 성공 결과 반환
        reconnect_result = ExecuteResult(
            success=True,
            result="reconnected result",
            agent_session_id="sess-recon",
            claude_session_id="sess-reconnect",
        )
        client.reconnect_stream = AsyncMock(return_value=reconnect_result)

        result = await client.execute("hello")

        assert result.success is True
        assert result.result == "reconnected result"
        client.reconnect_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect_retries_with_backoff(self, client):
        """재연결이 여러 번 실패하면 백오프 후 재시도한다"""
        import aiohttp

        # init 이벤트 후 연결 끊김
        init_line = b"event:init\n"
        init_data = b'data:{"agent_session_id":"sess-retry"}\n'
        init_end = b"\n"
        lines = [init_line, init_data, init_end]

        reader = AsyncMock()
        call_count = 0
        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(lines):
                result = lines[call_count]
                call_count += 1
                return result
            raise aiohttp.ClientPayloadError("Connection lost")
        reader.readline = AsyncMock(side_effect=readline_side_effect)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = reader
        client._session = _mock_session(mock_response)

        # reconnect_stream: 처음 2회 실패, 3번째 성공
        success_result = ExecuteResult(
            success=True,
            result="finally connected",
            agent_session_id="sess-retry",
            claude_session_id="sess-final",
        )
        client.reconnect_stream = AsyncMock(
            side_effect=[
                ConnectionLostError("fail 1"),
                ConnectionLostError("fail 2"),
                success_result,
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("hello")

        assert result.success is True
        assert result.result == "finally connected"
        assert client.reconnect_stream.call_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_all_retries_exhausted(self, client):
        """재연결 재시도를 모두 소진하면 실패 결과를 반환한다"""
        import aiohttp

        # init 이벤트 후 연결 끊김
        init_line = b"event:init\n"
        init_data = b'data:{"agent_session_id":"sess-exhaust"}\n'
        init_end = b"\n"
        lines = [init_line, init_data, init_end]

        reader = AsyncMock()
        call_count = 0
        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(lines):
                result = lines[call_count]
                call_count += 1
                return result
            raise aiohttp.ClientPayloadError("Connection lost")
        reader.readline = AsyncMock(side_effect=readline_side_effect)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = reader
        client._session = _mock_session(mock_response)

        # reconnect_stream: 항상 실패
        client.reconnect_stream = AsyncMock(
            side_effect=ConnectionLostError("still disconnected")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("hello")

        assert result.success is False
        assert "재시도 실패" in result.error

    @pytest.mark.asyncio
    async def test_reconnect_session_not_found(self, client):
        """재연결 시 세션이 이미 종료된 경우"""
        import aiohttp

        # init 이벤트 후 연결 끊김
        init_line = b"event:init\n"
        init_data = b'data:{"agent_session_id":"sess-gone"}\n'
        init_end = b"\n"
        lines = [init_line, init_data, init_end]

        reader = AsyncMock()
        call_count = 0
        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(lines):
                result = lines[call_count]
                call_count += 1
                return result
            raise aiohttp.ClientPayloadError("Connection lost")
        reader.readline = AsyncMock(side_effect=readline_side_effect)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = reader
        client._session = _mock_session(mock_response)

        client.reconnect_stream = AsyncMock(
            side_effect=SessionNotFoundError("session gone")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("hello")

        assert result.success is False
        assert "세션이 이미 종료됨" in result.error

    @pytest.mark.asyncio
    async def test_connection_lost_without_session_id(self, client):
        """init 이벤트 없이 바로 연결이 끊기면 재연결 불가"""
        import aiohttp

        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("Connection lost")
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = broken_reader
        client._session = _mock_session(mock_response)

        result = await client.execute("hello")

        assert result.success is False
        assert "세션 ID를 받지 못해" in result.error

    @pytest.mark.asyncio
    async def test_parse_sse_stream_raises_connection_lost(self, client):
        """_parse_sse_stream이 ClientError 발생 시 ConnectionLostError를 raise한다"""
        import aiohttp

        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("broken pipe")
        )
        mock_response = MagicMock()
        mock_response.content = broken_reader

        with pytest.raises(ConnectionLostError, match="broken pipe"):
            async for _ in client._parse_sse_stream(mock_response):
                pass

    @pytest.mark.asyncio
    async def test_parse_sse_stream_chunk_too_big_raises_connection_lost(self, client):
        """readline()이 ValueError('Chunk too big')를 raise하면 ConnectionLostError로 변환"""
        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=ValueError("Chunk too big")
        )
        mock_response = MagicMock()
        mock_response.content = broken_reader

        with pytest.raises(ConnectionLostError, match="SSE 라인 크기 초과"):
            async for _ in client._parse_sse_stream(mock_response):
                pass

    @pytest.mark.asyncio
    async def test_parse_sse_stream_other_value_error_propagates(self, client):
        """Chunk too big이 아닌 ValueError는 그대로 전파된다"""
        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=ValueError("some other value error")
        )
        mock_response = MagicMock()
        mock_response.content = broken_reader

        with pytest.raises(ValueError, match="some other value error"):
            async for _ in client._parse_sse_stream(mock_response):
                pass

    @pytest.mark.asyncio
    async def test_chunk_too_big_triggers_reconnect(self, client):
        """init 이벤트 수신 후 ValueError('Chunk too big') 발생 시 재연결"""
        init_line = b"event:init\n"
        init_data = b'data:{"agent_session_id":"sess-chunk"}\n'
        init_end = b"\n"
        lines = [init_line, init_data, init_end]

        reader = AsyncMock()
        call_count = 0

        async def readline_side_effect():
            nonlocal call_count
            if call_count < len(lines):
                result = lines[call_count]
                call_count += 1
                return result
            raise ValueError("Chunk too big")

        reader.readline = AsyncMock(side_effect=readline_side_effect)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = reader
        client._session = _mock_session(mock_response)

        # reconnect_stream mock: 성공 결과 반환
        reconnect_result = ExecuteResult(
            success=True,
            result="reconnected after chunk error",
            agent_session_id="sess-chunk",
            claude_session_id="sess-chunk-r",
        )
        client.reconnect_stream = AsyncMock(return_value=reconnect_result)

        result = await client.execute("hello")

        assert result.success is True
        assert result.result == "reconnected after chunk error"
        client.reconnect_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_uses_large_read_bufsize(self, client):
        """_get_session()이 aiohttp.ClientSession에 read_bufsize=2**25을 전달하는지 확인"""
        with patch("aiohttp.ClientSession") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.closed = False
            mock_cls.return_value = mock_instance

            # 기존 세션을 제거하여 새로 생성하도록 강제
            client._session = None

            session = await client._get_session()

            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["read_bufsize"] == 2**25


class TestClaudeOAuthTokenAPI:
    """SoulServiceClient Claude OAuth Token API 테스트"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    # --- set_claude_token ---

    @pytest.mark.asyncio
    async def test_set_claude_token_success(self, client):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True, "message": "토큰이 설정되었습니다."
        })
        client._session = _mock_session(mock_response)

        result = await client.set_claude_token("sk-ant-oat01-xxx")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_set_claude_token_error(self, client):
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": {"message": "invalid token"}})
        client._session = _mock_session(mock_response)

        with pytest.raises(SoulServiceError, match="토큰 설정 실패"):
            await client.set_claude_token("bad-token")

    @pytest.mark.asyncio
    async def test_set_claude_token_url(self, client):
        """set_claude_token이 올바른 URL을 호출하는지 확인"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        session = _mock_session(mock_response)
        client._session = session

        await client.set_claude_token("sk-ant-oat01-xxx")

        call_args = session.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url", "")
        assert url == "http://localhost:3105/auth/claude/token"
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert body["token"] == "sk-ant-oat01-xxx"

    # --- clear_claude_token ---

    @pytest.mark.asyncio
    async def test_clear_claude_token_success(self, client):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True, "message": "토큰이 삭제되었습니다."
        })
        client._session = _mock_session(mock_response, method="delete")

        result = await client.clear_claude_token()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_clear_claude_token_error(self, client):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": {"message": "internal error"}})
        client._session = _mock_session(mock_response, method="delete")

        with pytest.raises(SoulServiceError, match="토큰 삭제 실패"):
            await client.clear_claude_token()

    @pytest.mark.asyncio
    async def test_clear_claude_token_url(self, client):
        """clear_claude_token이 올바른 URL을 호출하는지 확인"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        session = _mock_session(mock_response, method="delete")
        client._session = session

        await client.clear_claude_token()

        session.delete.assert_called_once_with("http://localhost:3105/auth/claude/token")


class TestParseError:
    """_parse_error 테스트"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105")

    @pytest.mark.asyncio
    async def test_parse_error_with_error_field(self, client):
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"error": {"message": "bad request"}})
        result = await client._parse_error(mock_response)
        assert result == "bad request"

    @pytest.mark.asyncio
    async def test_parse_error_with_detail_field(self, client):
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={
            "detail": {"error": {"message": "not found"}}
        })
        result = await client._parse_error(mock_response)
        assert result == "not found"

    @pytest.mark.asyncio
    async def test_parse_error_json_failure(self, client):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(side_effect=Exception("parse error"))
        result = await client._parse_error(mock_response)
        assert result == "HTTP 500"


class TestPersistListening:
    """persist_listening 모드 테스트

    complete 이벤트 후에도 SSE 구독을 유지하는 동작을 검증합니다.
    """

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    def _make_persist_mock_session(self, post_response, get_responses):
        """post(execute)와 get(reconnect) 각각의 응답을 설정하는 mock session"""
        session = MagicMock()
        session.closed = False
        session.post.return_value = MockAsyncContextManager(post_response)
        session.get.side_effect = [
            MockAsyncContextManager(r) for r in get_responses
        ]
        return session

    @pytest.mark.asyncio
    async def test_persist_false_returns_after_complete(self, client):
        """persist_listening=False (기본): complete 후 즉시 반환"""
        sse_data = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-A"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"done"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)
        session = MagicMock()
        session.closed = False
        session.post.return_value = MockAsyncContextManager(mock_response)
        client._session = session

        result = await client.execute("hello", persist_listening=False)

        assert result.success
        assert result.agent_session_id == "sess-A"
        # persist_listening=False이면 GET /events/... 호출 없어야 함
        session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_true_resubscribes_after_complete(self, client):
        """persist_listening=True: complete 후 GET /events/.../stream으로 재구독"""
        # 초기 실행 응답
        post_sse = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-B"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"first response"}\n'
            b"\n"
        )
        post_response = MagicMock()
        post_response.status = 200
        post_response.content = _make_stream_reader(post_sse)

        # 재구독 응답: 세션이 없거나 비어있으면 즉시 빈 스트림 (종료 신호)
        get_response = MagicMock()
        get_response.status = 200
        get_response.content = _make_stream_reader(b"")  # 빈 스트림

        session = self._make_persist_mock_session(post_response, [get_response])
        client._session = session

        result = await client.execute(
            "hello",
            persist_listening=True,
            inactivity_timeout=5.0,
        )

        assert result.success
        assert result.agent_session_id == "sess-B"
        # GET /events/sess-B/stream 을 1회 호출했어야 함
        session.get.assert_called_once()
        call_url = session.get.call_args[0][0]
        assert "events/sess-B/stream" in call_url

    @pytest.mark.asyncio
    async def test_persist_true_handles_session_not_found(self, client):
        """persist_listening=True: 재구독 시 404 → SessionNotFoundError 처리 후 종료"""
        post_sse = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-C"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"initial"}\n'
            b"\n"
        )
        post_response = MagicMock()
        post_response.status = 200
        post_response.content = _make_stream_reader(post_sse)

        get_response = MagicMock()
        get_response.status = 404

        session = self._make_persist_mock_session(post_response, [get_response])
        client._session = session

        result = await client.execute(
            "hello",
            persist_listening=True,
            inactivity_timeout=5.0,
        )

        # 세션이 없어도 마지막 성공 결과를 반환해야 함
        assert result.success
        assert result.agent_session_id == "sess-C"

    @pytest.mark.asyncio
    async def test_persist_true_receives_new_events(self, client):
        """persist_listening=True: 재구독 후 새 이벤트를 수신하면 루프 계속"""
        post_sse = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-D"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"first"}\n'
            b"\n"
        )
        post_response = MagicMock()
        post_response.status = 200
        post_response.content = _make_stream_reader(post_sse)

        # 첫 번째 재구독: 새 이벤트 수신 (두 번째 응답)
        get_sse_1 = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-D"}\n'
            b"\n"
            b"event:text_delta\n"
            b'data:{"text":"new text"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"second"}\n'
            b"\n"
        )
        get_response_1 = MagicMock()
        get_response_1.status = 200
        get_response_1.content = _make_stream_reader(get_sse_1)

        # 두 번째 재구독: 빈 스트림 (종료)
        get_response_2 = MagicMock()
        get_response_2.status = 200
        get_response_2.content = _make_stream_reader(b"")

        received_deltas = []
        async def on_text_delta(text, event_id, parent_event_id):
            received_deltas.append(text)

        session = self._make_persist_mock_session(
            post_response, [get_response_1, get_response_2]
        )
        client._session = session

        result = await client.execute(
            "hello",
            persist_listening=True,
            inactivity_timeout=5.0,
            on_text_delta=on_text_delta,
        )

        # 두 번째 이벤트의 text_delta가 콜백으로 전달되었어야 함
        assert "new text" in received_deltas
        # GET을 2회 호출했어야 함
        assert session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_persist_true_inactivity_timeout(self, client):
        """persist_listening=True: 비활성 타임아웃 초과 시 마지막 결과 반환"""
        post_sse = (
            b"event:init\n"
            b'data:{"agent_session_id":"sess-E"}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"result":"done"}\n'
            b"\n"
        )
        post_response = MagicMock()
        post_response.status = 200
        post_response.content = _make_stream_reader(post_sse)

        # 재구독 응답이 영원히 블로킹되는 상황을 asyncio.TimeoutError로 시뮬레이션
        async def hanging_sse_events(*args, **kwargs):
            await asyncio.sleep(100)  # 타임아웃보다 훨씬 길게
            return ExecuteResult(success=True, result="")

        session = MagicMock()
        session.closed = False
        session.post.return_value = MockAsyncContextManager(post_response)

        get_response = MagicMock()
        get_response.status = 200
        get_response.content = _make_stream_reader(b"")
        session.get.return_value = MockAsyncContextManager(get_response)
        client._session = session

        # _persist_listen_loop 내부의 wait_for가 타임아웃을 처리
        # _persist_reconnect_once가 타임아웃 전에 반환하면 루프가 종료됨
        result = await client.execute(
            "hello",
            persist_listening=True,
            inactivity_timeout=0.01,  # 매우 짧은 타임아웃
        )

        # 타임아웃 후에도 마지막 성공 결과를 반환해야 함
        assert result.success
        assert result.agent_session_id == "sess-E"
