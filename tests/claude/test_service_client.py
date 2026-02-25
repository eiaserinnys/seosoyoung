"""SoulServiceClient 테스트

mock aiohttp 서버를 사용하여 HTTP + SSE 클라이언트 동작을 검증합니다.
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from seosoyoung.slackbot.claude.service_client import (
    SoulServiceClient,
    SoulServiceError,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    RateLimitError,
    ConnectionLostError,
    ExponentialBackoff,
    ExecuteResult,
    SSEEvent,
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


class TestSoulServiceClientExecute:
    """SoulServiceClient.execute() 테스트 (mock aiohttp)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_execute_conflict_raises(self, client):
        """409 응답 시 TaskConflictError"""
        mock_response = MagicMock()
        mock_response.status = 409
        client._session = _mock_session(mock_response)

        with pytest.raises(TaskConflictError):
            await client.execute("client1", "req1", "hello")

    @pytest.mark.asyncio
    async def test_execute_rate_limit_raises(self, client):
        """503 응답 시 RateLimitError"""
        mock_response = MagicMock()
        mock_response.status = 503
        client._session = _mock_session(mock_response)

        with pytest.raises(RateLimitError):
            await client.execute("client1", "req1", "hello")

    @pytest.mark.asyncio
    async def test_execute_generic_error_raises(self, client):
        """기타 에러 상태 코드 시 SoulServiceError"""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": {"message": "internal error"}})
        client._session = _mock_session(mock_response)

        with pytest.raises(SoulServiceError, match="internal error"):
            await client.execute("client1", "req1", "hello")

    @pytest.mark.asyncio
    async def test_execute_includes_tool_settings_in_body(self, client):
        """allowed_tools/disallowed_tools/use_mcp가 HTTP body에 포함되는지 확인"""
        sse_data = (
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
            "client1", "req1", "hello",
            allowed_tools=["Read", "Glob"],
            disallowed_tools=["Bash"],
            use_mcp=False,
        )

        # session.post가 호출된 json 데이터 확인
        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["allowed_tools"] == ["Read", "Glob"]
        assert body["disallowed_tools"] == ["Bash"]
        assert body["use_mcp"] is False

    @pytest.mark.asyncio
    async def test_execute_omits_none_tools_from_body(self, client):
        """allowed_tools/disallowed_tools가 None이면 body에서 생략"""
        sse_data = (
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)

        session = _mock_session(mock_response)
        client._session = session

        await client.execute("client1", "req1", "hello")

        call_kwargs = session.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "allowed_tools" not in body
        assert "disallowed_tools" not in body
        assert body["use_mcp"] is True  # 기본값


class TestSoulServiceClientIntervene:
    """SoulServiceClient.intervene() 테스트"""

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

        result = await client.intervene("client1", "req1", "추가 지시", "user1")
        assert result["queued"] is True

    @pytest.mark.asyncio
    async def test_intervene_not_found(self, client):
        """404 응답 시 TaskNotFoundError"""
        mock_response = MagicMock()
        mock_response.status = 404
        client._session = _mock_session(mock_response)

        with pytest.raises(TaskNotFoundError):
            await client.intervene("client1", "req1", "hello", "user1")

    @pytest.mark.asyncio
    async def test_intervene_not_running(self, client):
        """409 응답 시 TaskNotRunningError"""
        mock_response = MagicMock()
        mock_response.status = 409
        client._session = _mock_session(mock_response)

        with pytest.raises(TaskNotRunningError):
            await client.intervene("client1", "req1", "hello", "user1")


class TestSoulServiceClientAck:
    """SoulServiceClient.ack() 테스트"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_ack_success(self, client):
        mock_response = MagicMock()
        mock_response.status = 200
        client._session = _mock_session(mock_response)

        result = await client.ack("client1", "req1")
        assert result is True

    @pytest.mark.asyncio
    async def test_ack_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status = 404
        client._session = _mock_session(mock_response)

        result = await client.ack("client1", "req1")
        assert result is False


class TestSoulServiceClientReconnect:
    """SoulServiceClient.reconnect_stream() 테스트"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_reconnect_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status = 404
        client._session = _mock_session(mock_response, method="get")

        with pytest.raises(TaskNotFoundError):
            await client.reconnect_stream("client1", "req1")

    @pytest.mark.asyncio
    async def test_reconnect_success(self, client):
        """재연결 + complete 이벤트"""
        sse_data = (
            b"event:reconnected\n"
            b'data:{"type":"reconnected","status":"running","last_progress":"working..."}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"reconnect done","claude_session_id":"sess-r"}\n'
            b"\n"
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = _make_stream_reader(sse_data)
        client._session = _mock_session(mock_response, method="get")

        progress_texts = []
        async def on_progress(text):
            progress_texts.append(text)

        result = await client.reconnect_stream("client1", "req1", on_progress=on_progress)
        assert result.success is True
        assert result.result == "reconnect done"
        assert "[재연결됨]" in progress_texts[0]


class TestHandleSSEEvents:
    """_handle_sse_events 테스트 (SSE 스트림 처리)"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105")

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
    async def test_progress_callback(self, client):
        """progress 이벤트가 콜백을 호출하는지 확인"""
        sse_data = (
            b"event:progress\n"
            b'data:{"type":"progress","text":"thinking..."}\n'
            b"\n"
            b"event:complete\n"
            b'data:{"type":"complete","result":"done"}\n'
            b"\n"
        )

        mock_response = AsyncMock()
        mock_response.content = _make_stream_reader(sse_data)

        progress_texts = []

        async def on_progress(text):
            progress_texts.append(text)

        result = await client._handle_sse_events(mock_response, on_progress=on_progress)
        assert result.success is True
        assert "thinking..." in progress_texts

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


class TestSSEReconnection:
    """SSE 연결 끊김 시 자동 재연결 테스트"""

    @pytest.fixture
    def client(self):
        return SoulServiceClient(base_url="http://localhost:3105", token="test")

    @pytest.mark.asyncio
    async def test_connection_lost_triggers_reconnect(self, client):
        """연결 끊김 시 reconnect_stream()으로 재연결하여 결과를 받는다"""
        import aiohttp

        # 첫 번째 응답: SSE 스트림 도중 연결 끊김
        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("Connection lost")
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = broken_reader
        client._session = _mock_session(mock_response)

        # reconnect_stream mock: 성공 결과 반환
        reconnect_result = ExecuteResult(
            success=True,
            result="reconnected result",
            claude_session_id="sess-reconnect",
        )
        client.reconnect_stream = AsyncMock(return_value=reconnect_result)

        result = await client.execute("client1", "req1", "hello")

        assert result.success is True
        assert result.result == "reconnected result"
        assert result.claude_session_id == "sess-reconnect"
        client.reconnect_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect_retries_with_backoff(self, client):
        """재연결이 여러 번 실패하면 백오프 후 재시도한다"""
        import aiohttp

        # 첫 번째 응답: 연결 끊김
        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("Connection lost")
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = broken_reader
        client._session = _mock_session(mock_response)

        # reconnect_stream: 처음 2회 실패, 3번째 성공
        success_result = ExecuteResult(
            success=True,
            result="finally connected",
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
            result = await client.execute("client1", "req1", "hello")

        assert result.success is True
        assert result.result == "finally connected"
        assert client.reconnect_stream.call_count == 3

    @pytest.mark.asyncio
    async def test_reconnect_all_retries_exhausted(self, client):
        """재연결 재시도를 모두 소진하면 실패 결과를 반환한다"""
        import aiohttp

        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("Connection lost")
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = broken_reader
        client._session = _mock_session(mock_response)

        # reconnect_stream: 항상 실패
        client.reconnect_stream = AsyncMock(
            side_effect=ConnectionLostError("still disconnected")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("client1", "req1", "hello")

        assert result.success is False
        assert "재시도 실패" in result.error

    @pytest.mark.asyncio
    async def test_reconnect_task_not_found(self, client):
        """재연결 시 태스크가 이미 종료된 경우"""
        import aiohttp

        broken_reader = AsyncMock()
        broken_reader.readline = AsyncMock(
            side_effect=aiohttp.ClientPayloadError("Connection lost")
        )
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = broken_reader
        client._session = _mock_session(mock_response)

        client.reconnect_stream = AsyncMock(
            side_effect=TaskNotFoundError("task gone")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client.execute("client1", "req1", "hello")

        assert result.success is False
        assert "태스크가 이미 종료됨" in result.error

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
