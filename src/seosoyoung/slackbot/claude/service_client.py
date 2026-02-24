"""Claude Soul Service HTTP + SSE 클라이언트

seosoyoung-soul 서버와 통신하는 HTTP 클라이언트.
CLAUDE_EXECUTION_MODE=remote일 때 사용됩니다.

dorothy-bot의 claude_service_client.py 패턴을 seosoyoung에 맞게 적응.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# HTTP 타임아웃 (초)
HTTP_CONNECT_TIMEOUT = 10
HTTP_SOCK_READ_TIMEOUT = 180

# SSE 재연결 설정
SSE_RECONNECT_MAX_RETRIES = 5
SSE_RECONNECT_BASE_DELAY = 1.0
SSE_RECONNECT_MAX_DELAY = 16.0


# === 데이터 타입 ===

@dataclass
class SSEEvent:
    """Server-Sent Event 데이터"""
    event: str
    data: dict


@dataclass
class ExecuteResult:
    """soul 서버 실행 결과"""
    success: bool
    result: str
    claude_session_id: Optional[str] = None
    error: Optional[str] = None


# === 예외 ===

class SoulServiceError(Exception):
    """Soul Service 클라이언트 오류"""
    pass


class TaskConflictError(SoulServiceError):
    """태스크 충돌 오류 (이미 실행 중인 태스크 존재)"""
    pass


class TaskNotFoundError(SoulServiceError):
    """태스크를 찾을 수 없음"""
    pass


class TaskNotRunningError(SoulServiceError):
    """태스크가 실행 중이 아님"""
    pass


class RateLimitError(SoulServiceError):
    """동시 실행 제한 초과"""
    pass


class ConnectionLostError(SoulServiceError):
    """SSE 연결 끊김 (재시도 실패)"""
    pass


# === 유틸리티 ===

class ExponentialBackoff:
    """지수 백오프 유틸리티"""

    def __init__(
        self,
        base_delay: float = SSE_RECONNECT_BASE_DELAY,
        max_delay: float = SSE_RECONNECT_MAX_DELAY,
        max_retries: int = SSE_RECONNECT_MAX_RETRIES,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.attempt = 0

    def get_delay(self) -> float:
        delay = self.base_delay * (2 ** self.attempt)
        return min(delay, self.max_delay)

    def should_retry(self) -> bool:
        return self.attempt < self.max_retries

    def increment(self) -> None:
        self.attempt += 1

    def reset(self) -> None:
        self.attempt = 0


# === 클라이언트 ===

class SoulServiceClient:
    """seosoyoung-soul 서버 HTTP + SSE 클라이언트

    Task API를 사용하여 Claude Code를 원격 실행합니다.

    사용 예:
        client = SoulServiceClient(base_url="http://localhost:3105", token="xxx")
        result = await client.execute(
            client_id="seosoyoung_bot",
            request_id="thread_ts",
            prompt="안녕"
        )
    """

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                connect=HTTP_CONNECT_TIMEOUT,
                sock_read=HTTP_SOCK_READ_TIMEOUT,
                total=None,
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._build_headers(),
            )
        return self._session

    def _build_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "SoulServiceClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # === Task API ===

    async def execute(
        self,
        client_id: str,
        request_id: str,
        prompt: str,
        resume_session_id: Optional[str] = None,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> ExecuteResult:
        """Claude Code 실행 (SSE 스트리밍)"""
        session = await self._get_session()
        url = f"{self.base_url}/execute"

        data = {
            "client_id": client_id,
            "request_id": request_id,
            "prompt": prompt,
        }
        if resume_session_id:
            data["resume_session_id"] = resume_session_id

        async with session.post(url, json=data) as response:
            if response.status == 409:
                raise TaskConflictError(
                    f"이미 실행 중인 태스크가 있습니다: {client_id}:{request_id}"
                )
            elif response.status == 503:
                raise RateLimitError("동시 실행 제한을 초과했습니다")
            elif response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"실행 실패: {error}")

            return await self._handle_sse_events(
                response=response,
                on_progress=on_progress,
                on_compact=on_compact,
            )

    async def intervene(
        self,
        client_id: str,
        request_id: str,
        text: str,
        user: str,
    ) -> dict:
        """실행 중인 태스크에 개입 메시지 전송"""
        session = await self._get_session()
        url = f"{self.base_url}/tasks/{client_id}/{request_id}/intervene"

        data = {"text": text, "user": user}

        async with session.post(url, json=data) as response:
            if response.status == 202:
                return await response.json()
            elif response.status == 404:
                raise TaskNotFoundError(
                    f"태스크를 찾을 수 없습니다: {client_id}:{request_id}"
                )
            elif response.status == 409:
                raise TaskNotRunningError(
                    f"태스크가 실행 중이 아닙니다: {client_id}:{request_id}"
                )
            else:
                error = await self._parse_error(response)
                raise SoulServiceError(f"개입 메시지 전송 실패: {error}")

    async def ack(self, client_id: str, request_id: str) -> bool:
        """결과 수신 확인"""
        session = await self._get_session()
        url = f"{self.base_url}/tasks/{client_id}/{request_id}/ack"

        async with session.post(url) as response:
            if response.status == 200:
                return True
            elif response.status == 404:
                return False
            else:
                error = await self._parse_error(response)
                raise SoulServiceError(f"ack 실패: {error}")

    async def reconnect_stream(
        self,
        client_id: str,
        request_id: str,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> ExecuteResult:
        """태스크 SSE 스트림에 재연결"""
        session = await self._get_session()
        url = f"{self.base_url}/tasks/{client_id}/{request_id}/stream"

        async with session.get(url) as response:
            if response.status == 404:
                raise TaskNotFoundError(
                    f"태스크를 찾을 수 없습니다: {client_id}:{request_id}"
                )
            elif response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"스트림 재연결 실패: {error}")

            return await self._handle_sse_events(
                response=response,
                on_progress=on_progress,
                on_compact=on_compact,
            )

    async def health_check(self) -> dict:
        """헬스 체크"""
        session = await self._get_session()
        url = f"{self.base_url}/health"

        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise SoulServiceError("헬스 체크 실패")

    # === 헬퍼 메서드 ===

    async def _handle_sse_events(
        self,
        response: aiohttp.ClientResponse,
        on_progress: Optional[Callable[[str], Awaitable[None]]] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> ExecuteResult:
        """SSE 이벤트 스트림 처리"""
        result_text = ""
        result_claude_session_id = None
        error_message = None

        backoff = ExponentialBackoff()

        try:
            async for event in self._parse_sse_stream(response, backoff):
                if event.event == "progress":
                    text = event.data.get("text", "")
                    if on_progress and text:
                        await on_progress(text)

                elif event.event == "compact":
                    if on_compact:
                        await on_compact(
                            event.data.get("trigger", "auto"),
                            event.data.get("message", "컴팩트 실행됨"),
                        )

                elif event.event == "complete":
                    result_text = event.data.get("result", "")
                    result_claude_session_id = event.data.get("claude_session_id")

                elif event.event == "error":
                    error_message = event.data.get("message", "알 수 없는 오류")

                elif event.event == "reconnected":
                    last_progress = event.data.get("last_progress", "")
                    if last_progress and on_progress:
                        await on_progress(f"[재연결됨] {last_progress}")

        except asyncio.TimeoutError:
            error_message = "응답 대기 시간 초과"
        except ConnectionLostError as e:
            error_message = str(e)
        except aiohttp.ClientError as e:
            error_message = f"네트워크 오류: {e}"

        if error_message:
            return ExecuteResult(
                success=False,
                result=error_message,
                error=error_message,
            )

        return ExecuteResult(
            success=True,
            result=result_text,
            claude_session_id=result_claude_session_id,
        )

    async def _parse_sse_stream(
        self,
        response: aiohttp.ClientResponse,
        backoff: ExponentialBackoff,
    ) -> AsyncIterator[SSEEvent]:
        """SSE 스트림 파싱 (연결 끊김 시 지수 백오프 재시도)"""
        current_event = "message"
        current_data: list[str] = []

        while True:
            try:
                line_bytes = await asyncio.wait_for(
                    response.content.readline(),
                    timeout=HTTP_SOCK_READ_TIMEOUT,
                )

                backoff.reset()

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8").rstrip("\r\n")

                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    current_data.append(line[5:].strip())
                elif line.startswith(":"):
                    pass  # SSE comment (keepalive)
                elif line == "":
                    if current_data:
                        data_str = "\n".join(current_data)
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = {"raw": data_str}

                        yield SSEEvent(event=current_event, data=data)

                        current_event = "message"
                        current_data = []

            except asyncio.TimeoutError:
                raise

            except aiohttp.ClientError as e:
                if backoff.should_retry():
                    delay = backoff.get_delay()
                    logger.warning(
                        f"[SSE] 연결 끊김, 재시도 ({backoff.attempt + 1}/{backoff.max_retries}), "
                        f"{delay}초 후: {e}"
                    )
                    backoff.increment()
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise ConnectionLostError(
                        f"소울 서비스 연결이 끊어졌습니다 ({backoff.max_retries}회 재시도 실패)"
                    )

    async def _parse_error(self, response: aiohttp.ClientResponse) -> str:
        """에러 응답 파싱"""
        try:
            data = await response.json()
            if "error" in data:
                return data["error"].get("message", str(data["error"]))
            if "detail" in data:
                detail = data["detail"]
                if isinstance(detail, dict) and "error" in detail:
                    return detail["error"].get("message", str(detail["error"]))
                return str(detail)
            return str(data)
        except Exception:
            return f"HTTP {response.status}"
