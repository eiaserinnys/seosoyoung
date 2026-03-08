"""인터벤션(Intervention) 관리

실행 중인 스레드에 새 메시지가 도착했을 때의 처리를 담당합니다.
- PendingPrompt 저장/조회
- interrupt 전송 (agent_session_id 기반)

per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)


@dataclass
class PendingPrompt:
    """인터벤션 대기 중인 프롬프트 정보

    콜백 + opaque 컨텍스트만 저장합니다.
    Slack 필드(channel, say, client 등)는 presentation 컨텍스트에 포함됩니다.
    """
    prompt: str
    msg_ts: str
    on_compact: Any = None     # CompactCallback
    presentation: Any = None   # PresentationContext (opaque)
    role: Optional[str] = None
    user_message: Optional[str] = None
    on_result: Any = None      # ResultCallback
    session_id: Optional[str] = None
    # 세분화 이벤트 콜백
    on_thinking: Any = None       # (thinking_text, event_id, parent_event_id) -> None
    on_text_start: Any = None     # (event_id, parent_event_id) -> None
    on_text_delta: Any = None     # (text, event_id, parent_event_id) -> None
    on_text_end: Any = None       # (event_id, parent_event_id) -> None
    on_tool_start: Any = None     # (tool_name, tool_input, tool_use_id, event_id, parent_event_id) -> None
    on_tool_result: Any = None    # (result, tool_use_id, is_error, event_id, parent_event_id) -> None
    on_input_request: Any = None  # (request_id, questions, agent_session_id) -> None


class InterventionManager:
    """인터벤션 관리자

    실행 중인 스레드에 새 메시지가 도착하면:
    1. pending에 프롬프트 저장 (최신 것으로 덮어씀)
    2. 현재 실행 중인 세션에 agent_session_id 기반 intervene 전송
    """

    def __init__(self):
        self._pending_prompts: dict[str, PendingPrompt] = {}
        self._pending_lock = threading.Lock()

    def save_pending(self, thread_ts: str, pending: PendingPrompt):
        """pending 프롬프트 저장 (최신 것으로 덮어씀)"""
        with self._pending_lock:
            self._pending_prompts[thread_ts] = pending

    def pop_pending(self, thread_ts: str) -> Optional[PendingPrompt]:
        """pending 프롬프트를 꺼내고 제거"""
        with self._pending_lock:
            return self._pending_prompts.pop(thread_ts, None)

    @property
    def pending_prompts(self) -> dict[str, PendingPrompt]:
        """pending_prompts dict 직접 접근 (테스트용)"""
        return self._pending_prompts

    def fire_interrupt_remote(
        self,
        thread_ts: str,
        prompt: str,
        service_adapter,
        *,
        session_id: Optional[str] = None,
        pending_session_interventions: Optional[dict] = None,
        pending_session_lock: Optional[Any] = None,
    ):
        """Remote 모드: Soulstream에 HTTP intervene 요청 (agent_session_id 기반)

        session_id가 확보되어 있으면 즉시 인터벤션을 전송합니다.
        session_id가 없으면 (아직 미확보) 버퍼에 보관합니다.

        sync 스레드 컨텍스트(executor._run_with_lock 내부)에서 호출되므로
        run_in_new_loop로 격리된 이벤트 루프를 생성해 async 호출을 수행합니다.
        """
        from seosoyoung.utils.async_bridge import run_in_new_loop

        # 1. session_id가 있으면 즉시 인터벤션 전송
        if session_id and service_adapter:
            try:
                run_in_new_loop(
                    service_adapter.intervene(
                        agent_session_id=session_id,
                        text=prompt,
                        user="intervention",
                    )
                )
                logger.info(f"[Remote] 인터벤션 전송 완료: thread={thread_ts}, session={session_id}")
                return
            except Exception as e:
                logger.warning(f"[Remote] 인터벤션 전송 실패: thread={thread_ts}, {e}")
                return

        # 2. session_id 미확보 → 버퍼에 보관
        if pending_session_interventions is not None and pending_session_lock is not None:
            with pending_session_lock:
                if thread_ts not in pending_session_interventions:
                    pending_session_interventions[thread_ts] = []
                pending_session_interventions[thread_ts].append((prompt, "intervention"))
            logger.info(f"[Remote] 인터벤션 버퍼에 보관 (session_id 미확보): thread={thread_ts}")
            return

        logger.warning(f"[Remote] 인터벤션 전송 불가: session_id 없음 (thread={thread_ts})")
