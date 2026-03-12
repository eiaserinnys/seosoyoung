"""인터벤션(Intervention) 관리

실행 중인 스레드에 새 메시지가 도착했을 때의 처리를 담당합니다.
- Soulstream에 HTTP intervene 요청 전송 (agent_session_id 기반)

per-session 아키텍처: agent_session_id가 유일한 식별자.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class InterventionManager:
    """인터벤션 관리자

    실행 중인 스레드에 새 메시지가 도착하면:
    현재 실행 중인 세션에 agent_session_id 기반 intervene 전송
    """

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
        """Soulstream에 HTTP intervene 요청 (agent_session_id 기반)

        session_id가 확보되어 있으면 즉시 인터벤션을 전송합니다.
        session_id가 없으면 (아직 미확보) 버퍼에 보관합니다.

        sync 스레드 컨텍스트에서 호출되므로
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
