"""claude/ 모듈 내부 Protocol 정의

외부 의존성(TrackedCard, Config 등)을 제거하기 위한 인터페이스 타입입니다.
런타임 체크를 지원하여 duck-typing 호환 객체를 받을 수 있습니다.
"""

from typing import Any, Callable, Coroutine, Optional, Protocol, runtime_checkable


@runtime_checkable
class CardInfo(Protocol):
    """트렐로 카드 정보 Protocol (TrackedCard 대체)

    claude/ 모듈이 필요로 하는 카드 속성만 정의합니다.
    """

    @property
    def card_id(self) -> str: ...

    @property
    def card_name(self) -> str: ...

    @property
    def card_url(self) -> str: ...

    @property
    def list_key(self) -> str: ...

    @property
    def has_execute(self) -> bool: ...

    @property
    def session_id(self) -> Optional[str]: ...

    @property
    def dm_thread_ts(self) -> Optional[str]: ...


@runtime_checkable
class SlackClient(Protocol):
    """Slack WebClient Protocol

    claude/ 모듈이 사용하는 Slack API 메서드만 정의합니다.
    """

    def chat_postMessage(self, **kwargs) -> dict: ...
    def chat_update(self, **kwargs) -> dict: ...


# Callback 타입 별칭
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]]
CompactCallback = Callable[[str, str], Coroutine[Any, Any, None]]
SayFunction = Callable[..., Any]
UpdateMessageFn = Callable[..., None]  # (client, channel, ts, text, *, blocks=None) -> None

# OM(Observational Memory) 콜백 타입
PrepareMemoryFn = Callable[
    [str, Optional[str], Optional[str], Optional[str]],
    tuple[Optional[str], str],
]  # (thread_ts, channel, session_id, prompt) -> (memory_prompt, anchor_ts)
TriggerObservationFn = Callable[..., None]  # (thread_ts, user_id, prompt, collected, anchor_ts) -> None
OnCompactOMFlagFn = Callable[[str], None]  # (thread_ts) -> None
