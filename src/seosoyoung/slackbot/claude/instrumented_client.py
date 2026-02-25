"""관찰 가능한 Claude SDK 클라이언트

Agent SDK의 ClaudeSDKClient를 서브클래스하여,
SDK가 내부적으로 skip하는 이벤트(rate_limit_event 등)를
raw 스트림 단계에서 가로채어 관찰할 수 있게 한다.

주의: _query는 private 속성이므로 SDK 내부 리팩토링에 취약하다.
"""

import logging
from typing import AsyncIterator, Callable, Optional

try:
    from claude_agent_sdk import ClaudeSDKClient
    from claude_agent_sdk._errors import CLIConnectionError
    from claude_agent_sdk.types import Message, ResultMessage
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    # 더미 클래스
    class ClaudeSDKClient:
        pass
    class CLIConnectionError(Exception):
        pass
    class Message:
        pass
    class ResultMessage:
        pass

logger = logging.getLogger(__name__)

# 콜백 타입
RateLimitCallback = Callable[[dict], None]
UnknownEventCallback = Callable[[str, dict], None]

# Agent SDK가 파싱하는 알려진 메시지 타입
_KNOWN_MESSAGE_TYPES = frozenset({
    "user", "assistant", "system", "result",
})


class InstrumentedClaudeClient(ClaudeSDKClient):
    """rate_limit_event 등 SDK가 skip하는 이벤트를 관찰할 수 있는 확장 클라이언트.

    사용법:
        client = InstrumentedClaudeClient(
            options=options,
            on_rate_limit=my_rate_limit_handler,
            on_unknown_event=my_unknown_handler,
        )
    """

    def __init__(
        self,
        *args,
        on_rate_limit: Optional[RateLimitCallback] = None,
        on_unknown_event: Optional[UnknownEventCallback] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._on_rate_limit = on_rate_limit
        self._on_unknown_event = on_unknown_event

    async def receive_messages(self) -> AsyncIterator[Message]:
        """receive_messages를 오버라이드하여 raw 스트림에서 이벤트를 관찰.

        SDK의 parse_message()가 None을 반환하는 이벤트도
        raw dict 단계에서 콜백으로 전달한다.
        """
        if not self._query:
            raise CLIConnectionError("Not connected. Call connect() first.")

        from claude_agent_sdk._internal.message_parser import parse_message

        async for data in self._query.receive_messages():
            # raw dict 단계에서 관심 이벤트 관찰
            if isinstance(data, dict):
                msg_type = data.get("type")
                if msg_type == "rate_limit_event":
                    self._handle_rate_limit(data)
                elif msg_type and msg_type not in _KNOWN_MESSAGE_TYPES:
                    self._handle_unknown_event(msg_type, data)

            # 정상 파싱 경로 (SDK와 동일)
            message = parse_message(data)
            if message is not None:
                yield message

    def _handle_rate_limit(self, data: dict) -> None:
        """rate_limit_event 관찰."""
        if self._on_rate_limit:
            try:
                self._on_rate_limit(data)
            except Exception as e:
                logger.warning(f"rate_limit 콜백 오류: {e}")

    def _handle_unknown_event(self, msg_type: str, data: dict) -> None:
        """unknown event 관찰."""
        if self._on_unknown_event:
            try:
                self._on_unknown_event(msg_type, data)
            except Exception as e:
                logger.warning(f"unknown event 콜백 오류: {e}")
