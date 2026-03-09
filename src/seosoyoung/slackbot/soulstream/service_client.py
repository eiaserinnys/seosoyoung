"""Soulstream Service HTTP + SSE 클라이언트

Soulstream 서버(독립 soul-server, 기본 포트 4105)와 통신하는 HTTP 클라이언트.
per-session 아키텍처: agent_session_id가 유일한 식별자.
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
    id: Optional[str] = None


@dataclass
class ExecuteResult:
    """Soulstream 서버 실행 결과"""
    success: bool
    result: str
    agent_session_id: Optional[str] = None
    claude_session_id: Optional[str] = None
    error: Optional[str] = None


# === 예외 ===

class SoulServiceError(Exception):
    """Soul Service 클라이언트 오류"""
    pass


class SessionConflictError(SoulServiceError):
    """세션 충돌 오류 (이미 실행 중인 세션)"""
    pass


class SessionNotFoundError(SoulServiceError):
    """세션을 찾을 수 없음"""
    pass


class SessionNotRunningError(SoulServiceError):
    """세션이 실행 중이 아님"""
    pass


class RateLimitError(SoulServiceError):
    """동시 실행 제한 초과"""
    pass


class ConnectionLostError(SoulServiceError):
    """SSE 연결 끊김 (재시도 실패)

    Attributes:
        agent_session_id: init 이벤트에서 확보한 세션 ID (없으면 None).
            _handle_sse_events에서 init 이후 연결이 끊긴 경우 이 값이 설정되어
            execute()에서 재연결에 활용할 수 있습니다.
    """
    def __init__(self, message: str, agent_session_id: str | None = None):
        super().__init__(message)
        self.agent_session_id = agent_session_id


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
    """Soulstream 서버 HTTP + SSE 클라이언트

    per-session API를 사용하여 Claude Code를 원격 실행합니다.
    agent_session_id가 유일한 식별자입니다.

    사용 예:
        client = SoulServiceClient(base_url="http://localhost:4105", token="xxx")
        result = await client.execute(prompt="안녕")
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
                sock_read=None,   # 개별 SSE 라인 읽기에 타임아웃 없음 (Claude 실행이 오래 걸릴 수 있음)
                total=None,       # 전체 스트림 타임아웃 없음 (테스트 실행 등 장시간 작업 지원)
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._build_headers(),
                read_bufsize=2**20,  # 1MB (기본 64KB → 1MB, _high_water = 2MB)
            )
        return self._session

    def _build_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
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

    # === Session API ===

    async def execute(
        self,
        prompt: str,
        agent_session_id: Optional[str] = None,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_debug: Optional[Callable[[str], Awaitable[None]]] = None,
        on_session: Optional[Callable[[str], Awaitable[None]]] = None,
        on_credential_alert: Optional[Callable[[dict], Awaitable[None]]] = None,
        *,
        # 세분화 이벤트 콜백
        on_thinking: Optional[Callable] = None,
        on_text_start: Optional[Callable] = None,
        on_text_delta: Optional[Callable] = None,
        on_text_end: Optional[Callable] = None,
        on_tool_start: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
        on_input_request: Optional[Callable] = None,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        use_mcp: bool = True,
    ) -> ExecuteResult:
        """Claude Code 실행 (SSE 스트리밍, 연결 끊김 시 자동 재연결)

        POST /execute → SSE 응답. 첫 이벤트 init에서 agent_session_id를 읽습니다.

        Args:
            prompt: 실행할 프롬프트
            agent_session_id: 기존 세션 ID (없으면 새 세션 생성, 있으면 resume)
            on_compact: 컴팩션 콜백
            on_debug: 디버그 메시지 콜백 (rate_limit 경고 등)
            on_session: 세션 ID 조기 통지 콜백 (agent_session_id: str)
            on_credential_alert: 크레덴셜 알림 콜백 (data: dict)
            on_input_request: AskUserQuestion 이벤트 콜백 (request_id, questions, agent_session_id)
            allowed_tools: 허용 도구 목록 (None이면 서버 기본값 사용)
            disallowed_tools: 금지 도구 목록
            use_mcp: MCP 서버 연결 여부
        """
        session = await self._get_session()
        url = f"{self.base_url}/execute"

        data = {
            "prompt": prompt,
            "use_mcp": use_mcp,
        }
        if agent_session_id:
            data["agent_session_id"] = agent_session_id
        if allowed_tools is not None:
            data["allowed_tools"] = allowed_tools
        if disallowed_tools is not None:
            data["disallowed_tools"] = disallowed_tools

        backoff = ExponentialBackoff()
        resolved_session_id = agent_session_id  # init 이벤트에서 갱신됨

        async with session.post(url, json=data) as response:
            if response.status == 409:
                raise SessionConflictError(
                    f"이미 실행 중인 세션이 있습니다: {agent_session_id}"
                )
            elif response.status == 503:
                raise RateLimitError("동시 실행 제한을 초과했습니다")
            elif response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"실행 실패: {error}")

            try:
                result = await self._handle_sse_events(
                    response=response,
                    on_compact=on_compact,
                    on_debug=on_debug,
                    on_session=on_session,
                    on_credential_alert=on_credential_alert,
                    on_thinking=on_thinking,
                    on_text_start=on_text_start,
                    on_text_delta=on_text_delta,
                    on_text_end=on_text_end,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                    on_input_request=on_input_request,
                )
                # init 이벤트에서 읽은 session_id를 보존
                if result.agent_session_id:
                    resolved_session_id = result.agent_session_id
                return result
            except ConnectionLostError as e:
                # init 이벤트에서 이미 session_id를 받았을 수 있음
                if e.agent_session_id:
                    resolved_session_id = e.agent_session_id

        # 연결 끊김 → reconnect_stream()으로 새 HTTP 요청을 보내 재연결
        if not resolved_session_id:
            return ExecuteResult(
                success=False,
                result="연결 끊김: 세션 ID를 받지 못해 재연결할 수 없습니다",
                error="연결 끊김: 세션 ID를 받지 못해 재연결할 수 없습니다",
            )

        while backoff.should_retry():
            delay = backoff.get_delay()
            logger.warning(
                f"[SSE] 연결 끊김, 재연결 시도 ({backoff.attempt + 1}/{backoff.max_retries}), "
                f"{delay}초 후"
            )
            backoff.increment()
            await asyncio.sleep(delay)

            try:
                return await self.reconnect_stream(
                    resolved_session_id, on_compact, on_debug,
                    on_credential_alert,
                    on_thinking=on_thinking,
                    on_text_start=on_text_start,
                    on_text_delta=on_text_delta,
                    on_text_end=on_text_end,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                    on_input_request=on_input_request,
                )
            except ConnectionLostError:
                continue
            except SessionNotFoundError:
                return ExecuteResult(
                    success=False,
                    result="재연결 실패: 세션이 이미 종료됨",
                    error="재연결 실패: 세션이 이미 종료됨",
                )

        return ExecuteResult(
            success=False,
            result=f"Soulstream 연결이 끊어졌습니다 ({backoff.max_retries}회 재시도 실패)",
            error=f"Soulstream 연결이 끊어졌습니다 ({backoff.max_retries}회 재시도 실패)",
        )

    async def intervene(
        self,
        agent_session_id: str,
        text: str,
        user: str,
        *,
        attachment_paths: Optional[List[str]] = None,
    ) -> dict:
        """세션에 개입 메시지 전송

        POST /sessions/{agent_session_id}/intervene
        - 실행 중이면 intervention queue에 추가
        - 완료된 세션이면 자동 resume
        """
        session = await self._get_session()
        url = f"{self.base_url}/sessions/{agent_session_id}/intervene"

        data = {"text": text, "user": user}
        if attachment_paths:
            data["attachment_paths"] = attachment_paths

        async with session.post(url, json=data) as response:
            if response.status == 202:
                return await response.json()
            elif response.status == 404:
                raise SessionNotFoundError(
                    f"세션을 찾을 수 없습니다: {agent_session_id}"
                )
            elif response.status == 409:
                raise SessionNotRunningError(
                    f"세션이 실행 중이 아닙니다: {agent_session_id}"
                )
            else:
                error = await self._parse_error(response)
                raise SoulServiceError(f"개입 메시지 전송 실패: {error}")

    async def reconnect_stream(
        self,
        agent_session_id: str,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_debug: Optional[Callable[[str], Awaitable[None]]] = None,
        on_credential_alert: Optional[Callable[[dict], Awaitable[None]]] = None,
        *,
        # 세분화 이벤트 콜백
        on_thinking: Optional[Callable] = None,
        on_text_start: Optional[Callable] = None,
        on_text_delta: Optional[Callable] = None,
        on_text_end: Optional[Callable] = None,
        on_tool_start: Optional[Callable] = None,
        on_tool_result: Optional[Callable] = None,
        on_input_request: Optional[Callable] = None,
    ) -> ExecuteResult:
        """세션 SSE 스트림에 재연결

        GET /events/{agent_session_id}/stream
        """
        session = await self._get_session()
        url = f"{self.base_url}/events/{agent_session_id}/stream"

        async with session.get(url) as response:
            if response.status == 404:
                raise SessionNotFoundError(
                    f"세션을 찾을 수 없습니다: {agent_session_id}"
                )
            elif response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"스트림 재연결 실패: {error}")

            return await self._handle_sse_events(
                response=response,
                on_compact=on_compact,
                on_debug=on_debug,
                on_credential_alert=on_credential_alert,
                on_thinking=on_thinking,
                on_text_start=on_text_start,
                on_text_delta=on_text_delta,
                on_text_end=on_text_end,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
                on_input_request=on_input_request,
            )

    async def respond_to_input_request(
        self,
        agent_session_id: str,
        request_id: str,
        answers: dict,
    ) -> dict:
        """AskUserQuestion에 대한 사용자 응답 전달

        POST /sessions/{agent_session_id}/respond

        Args:
            agent_session_id: 세션 식별자
            request_id: input_request 이벤트의 request_id
            answers: {question_text: selected_label} 형태의 응답

        Returns:
            {"delivered": True, "request_id": "..."}

        Raises:
            SessionNotFoundError: 세션을 찾을 수 없음
            SessionNotRunningError: 세션이 실행 중이 아님
            SoulServiceError: 기타 오류
        """
        session = await self._get_session()
        url = f"{self.base_url}/sessions/{agent_session_id}/respond"

        data = {
            "request_id": request_id,
            "answers": answers,
        }

        async with session.post(url, json=data) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                raise SessionNotFoundError(
                    f"세션을 찾을 수 없습니다: {agent_session_id}"
                )
            elif response.status == 409:
                raise SessionNotRunningError(
                    f"세션이 실행 중이 아닙니다: {agent_session_id}"
                )
            elif response.status == 422:
                error = await self._parse_error(response)
                raise SoulServiceError(f"대기 중인 요청 없음: {error}")
            else:
                error = await self._parse_error(response)
                raise SoulServiceError(f"응답 전달 실패: {error}")

    async def health_check(self) -> dict:
        """헬스 체크"""
        session = await self._get_session()
        url = f"{self.base_url}/health"

        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise SoulServiceError("헬스 체크 실패")

    # === Credential Profile API ===

    async def list_profiles(self) -> dict:
        """프로필 목록 조회 (GET /profiles)

        Returns:
            {"profiles": [...], "active": "profile_name" | None}
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles"

        async with session.get(url) as response:
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"프로필 목록 조회 실패: {error}")
            return await response.json()

    async def get_rate_limits(self) -> dict:
        """전체 프로필 rate limit 조회 (GET /profiles/rate-limits)

        Returns:
            {"active_profile": str, "profiles": [...]}
            Rate limit tracking 비활성 시 빈 profiles 반환
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles/rate-limits"

        async with session.get(url) as response:
            if response.status == 503:
                return {"active_profile": None, "profiles": []}
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"Rate limit 조회 실패: {error}")
            return await response.json()

    async def save_profile(self, name: str) -> dict:
        """현재 크레덴셜을 프로필로 저장 (POST /profiles/{name})

        Returns:
            {"name": str, "saved": True}
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles/{name}"

        async with session.post(url) as response:
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"프로필 저장 실패: {error}")
            return await response.json()

    async def activate_profile(self, name: str) -> dict:
        """프로필 활성화 (POST /profiles/{name}/activate)

        Returns:
            {"activated": str}
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles/{name}/activate"

        async with session.post(url) as response:
            if response.status == 404:
                raise SoulServiceError(f"프로필을 찾을 수 없습니다: {name}")
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"프로필 활성화 실패: {error}")
            return await response.json()

    async def delete_profile(self, name: str) -> dict:
        """프로필 삭제 (DELETE /profiles/{name})

        Returns:
            {"deleted": True, "name": str}
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles/{name}"

        async with session.delete(url) as response:
            if response.status == 404:
                raise SoulServiceError(f"프로필을 찾을 수 없습니다: {name}")
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"프로필 삭제 실패: {error}")
            return await response.json()

    async def get_current_email(self) -> Optional[str]:
        """현재 크레덴셜의 계정 이메일 조회 (GET /profiles/email)

        Returns:
            이메일 주소 또는 None (이메일 없거나 크레덴셜에 포함되지 않음)
        """
        session = await self._get_session()
        url = f"{self.base_url}/profiles/email"

        async with session.get(url) as response:
            if response.status == 404:
                return None
            if response.status != 200:
                error = await self._parse_error(response)
                raise SoulServiceError(f"이메일 조회 실패: {error}")
            data = await response.json()
            return data.get("email")

    # === 헬퍼 메서드 ===

    async def _handle_sse_events(
        self,
        response: aiohttp.ClientResponse,
        on_compact: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_debug: Optional[Callable[[str], Awaitable[None]]] = None,
        on_session: Optional[Callable[[str], Awaitable[None]]] = None,
        on_credential_alert: Optional[Callable[[dict], Awaitable[None]]] = None,
        # 세분화 이벤트 콜백
        on_thinking: Optional[Callable] = None,       # (thinking_text, event_id, parent_event_id) -> None
        on_text_start: Optional[Callable] = None,     # (event_id, parent_event_id) -> None
        on_text_delta: Optional[Callable] = None,     # (text, event_id, parent_event_id) -> None
        on_text_end: Optional[Callable] = None,       # (event_id, parent_event_id) -> None
        on_tool_start: Optional[Callable] = None,     # (tool_name, tool_input, tool_use_id, event_id, parent_event_id) -> None
        on_tool_result: Optional[Callable] = None,    # (result, tool_use_id, is_error, event_id, parent_event_id) -> None
        on_input_request: Optional[Callable] = None,  # (request_id, questions, agent_session_id) -> None
    ) -> ExecuteResult:
        """SSE 이벤트 스트림 처리

        ConnectionLostError가 발생하면 이미 확보한 agent_session_id를 에러에
        첨부하여 상위 레이어로 전파합니다.
        재연결은 execute()에서 reconnect_stream()을 통해 처리합니다.
        """
        result_text = ""
        result_agent_session_id = None
        result_claude_session_id = None
        error_message = None

        try:
            async for event in self._parse_sse_stream(response):
                if event.event == "init":
                    # 첫 이벤트: agent_session_id 확보
                    result_agent_session_id = event.data.get("agent_session_id", "")
                    if on_session and result_agent_session_id:
                        await on_session(result_agent_session_id)

                elif event.event == "session":
                    # 하위 호환: 기존 session 이벤트도 처리
                    session_id = event.data.get("session_id", "")
                    if not result_agent_session_id and session_id:
                        result_agent_session_id = session_id
                        if on_session:
                            await on_session(session_id)

                elif event.event == "compact":
                    if on_compact:
                        await on_compact(
                            event.data.get("trigger", "auto"),
                            event.data.get("message", "컴팩트 실행됨"),
                        )

                elif event.event == "debug":
                    message = event.data.get("message", "")
                    if on_debug and message:
                        await on_debug(message)

                elif event.event == "complete":
                    result_text = event.data.get("result", "")
                    result_claude_session_id = event.data.get("claude_session_id")

                elif event.event == "error":
                    error_message = event.data.get("message", "알 수 없는 오류")

                elif event.event == "credential_alert":
                    if on_credential_alert:
                        await on_credential_alert(event.data)

                elif event.event == "thinking":
                    if on_thinking:
                        eid = int(event.id) if event.id is not None else None
                        await on_thinking(
                            event.data.get("thinking", ""),
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "text_start":
                    if on_text_start:
                        eid = int(event.id) if event.id is not None else None
                        await on_text_start(
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "text_delta":
                    if on_text_delta:
                        eid = int(event.id) if event.id is not None else None
                        await on_text_delta(
                            event.data.get("text", ""),
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "text_end":
                    if on_text_end:
                        eid = int(event.id) if event.id is not None else None
                        await on_text_end(
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "tool_start":
                    if on_tool_start:
                        eid = int(event.id) if event.id is not None else None
                        await on_tool_start(
                            event.data.get("tool_name", ""),
                            event.data.get("tool_input", {}),
                            event.data.get("tool_use_id", ""),
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "tool_result":
                    if on_tool_result:
                        eid = int(event.id) if event.id is not None else None
                        await on_tool_result(
                            event.data.get("result", ""),
                            event.data.get("tool_use_id", ""),
                            event.data.get("is_error", False),
                            eid,
                            event.data.get("parent_event_id"),
                        )

                elif event.event == "input_request":
                    if on_input_request:
                        await on_input_request(
                            event.data.get("request_id", ""),
                            event.data.get("questions", []),
                            result_agent_session_id or "",
                        )

        except ConnectionLostError as e:
            # 확보한 agent_session_id를 에러에 첨부하여 재연결에 활용
            raise ConnectionLostError(
                str(e), agent_session_id=result_agent_session_id,
            ) from e
        except asyncio.TimeoutError:
            error_message = "응답 대기 시간 초과"
            logger.error("[SSE] asyncio.TimeoutError: 전체 스트림 10분 제한 초과")
        except aiohttp.ClientError as e:
            error_message = f"네트워크 오류: {e}"
            logger.error(f"[SSE] aiohttp.ClientError: {e}")

        if error_message:
            return ExecuteResult(
                success=False,
                result=error_message,
                agent_session_id=result_agent_session_id,
                error=error_message,
            )

        return ExecuteResult(
            success=True,
            result=result_text,
            agent_session_id=result_agent_session_id,
            claude_session_id=result_claude_session_id,
        )

    async def _parse_sse_stream(
        self,
        response: aiohttp.ClientResponse,
    ) -> AsyncIterator[SSEEvent]:
        """SSE 스트림 파싱

        연결 끊김 시 ConnectionLostError를 발생시킵니다.
        재연결은 상위 레이어(execute)에서 reconnect_stream()을 통해 처리합니다.
        """
        current_event = "message"
        current_data: list[str] = []
        current_id: Optional[str] = None
        last_event_name = "none"  # 로깅용: 마지막으로 수신한 이벤트 이름

        while True:
            try:
                line_bytes = await response.content.readline()

                if not line_bytes:
                    logger.debug(f"[SSE] 스트림 종료 (마지막 이벤트: {last_event_name})")
                    break

                line = line_bytes.decode("utf-8").rstrip("\r\n")

                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    current_data.append(line[5:].strip())
                elif line.startswith("id:"):
                    current_id = line[3:].strip()
                elif line.startswith(":"):
                    pass  # SSE comment (keepalive)
                elif line == "":
                    if current_data:
                        data_str = "\n".join(current_data)
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = {"raw": data_str}

                        last_event_name = current_event
                        yield SSEEvent(event=current_event, data=data, id=current_id)

                        current_event = "message"
                        current_data = []
                        current_id = None

            except ValueError as e:
                # aiohttp.streams.StreamReader.readline()이 _high_water(= read_bufsize * 2)를
                # 초과하는 라인을 만나면 ValueError("Chunk too big")를 raise한다.
                # See: aiohttp/streams.py, StreamReader.readline()
                if "Chunk too big" in str(e):
                    logger.error(
                        f"[SSE] SSE 라인이 버퍼 크기를 초과했습니다 "
                        f"(마지막 이벤트: {last_event_name}): {e}"
                    )
                    raise ConnectionLostError(
                        f"SSE 라인 크기 초과: {e}"
                    )
                raise  # Chunk too big이 아닌 ValueError는 그대로 전파

            except asyncio.TimeoutError:
                logger.error(
                    f"[SSE] 전체 스트림 타임아웃 발생 (마지막 이벤트: {last_event_name})"
                )
                raise

            except aiohttp.ClientError as e:
                logger.error(
                    f"[SSE] 네트워크 오류로 연결 끊김 (마지막 이벤트: {last_event_name}): {e}"
                )
                raise ConnectionLostError(
                    f"Soulstream 연결이 끊어졌습니다: {e}"
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


# === 하위 호환 별칭 ===
# 기존 코드에서 TaskConflictError 등을 import하는 경우를 위한 별칭
TaskConflictError = SessionConflictError
TaskNotFoundError = SessionNotFoundError
TaskNotRunningError = SessionNotRunningError
