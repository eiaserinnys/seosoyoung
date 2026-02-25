"""인터벤션(Intervention) 관리

실행 중인 스레드에 새 메시지가 도착했을 때의 처리를 담당합니다.
- PendingPrompt 저장/조회
- interrupt 전송 (local/remote)
"""

import logging
import threading
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingPrompt:
    """인터벤션 대기 중인 프롬프트 정보

    콜백 + opaque 컨텍스트만 저장합니다.
    Slack 필드(channel, say, client 등)는 presentation 컨텍스트에 포함됩니다.
    """
    prompt: str
    msg_ts: str
    on_progress: Any = None    # ProgressCallback
    on_compact: Any = None     # CompactCallback
    presentation: Any = None   # PresentationContext (opaque)
    role: Optional[str] = None
    user_message: Optional[str] = None
    on_result: Any = None      # ResultCallback
    session_id: Optional[str] = None


class InterventionManager:
    """인터벤션 관리자

    실행 중인 스레드에 새 메시지가 도착하면:
    1. pending에 프롬프트 저장 (최신 것으로 덮어씀)
    2. 현재 실행 중인 runner/adapter에 interrupt 전송
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

    def fire_interrupt_local(self, thread_ts: str):
        """Local 모드: 모듈 레지스트리에서 runner를 찾아 interrupt 전송"""
        from seosoyoung.slackbot.claude.agent_runner import get_runner

        runner = get_runner(thread_ts)
        if runner:
            try:
                runner.interrupt()
                logger.info(f"인터럽트 전송 완료: thread={thread_ts}")
            except Exception as e:
                logger.warning(f"인터럽트 전송 실패 (무시): thread={thread_ts}, {e}")
        else:
            logger.warning(f"인터럽트 전송 불가: 실행 중인 runner 없음 (thread={thread_ts})")

    def fire_interrupt_remote(
        self,
        thread_ts: str,
        prompt: str,
        active_remote_requests: dict[str, str],
        service_adapter,
    ):
        """Remote 모드: soul 서버에 HTTP intervene 요청"""
        request_id = active_remote_requests.get(thread_ts)
        if request_id and service_adapter:
            try:
                from seosoyoung.utils.async_bridge import run_in_new_loop
                run_in_new_loop(
                    service_adapter.intervene(
                        request_id=request_id,
                        text=prompt,
                        user="intervention",
                    )
                )
                logger.info(f"[Remote] 인터벤션 전송 완료: thread={thread_ts}")
            except Exception as e:
                logger.warning(f"[Remote] 인터벤션 전송 실패 (무시): thread={thread_ts}, {e}")
        else:
            logger.warning(f"[Remote] 인터벤션 전송 불가: request_id 없음 (thread={thread_ts})")
