"""재시작 관리

재시작 대기 상태 및 확인 프로세스를 관리합니다.
"""

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RestartType(Enum):
    """재시작 유형"""
    UPDATE = 42   # git pull 후 재시작 (supervisor exit → watchdog이 git pull)
    RESTART = 43  # 봇 프로세스만 재시작 (supervisor가 pm.restart)
    RESTART_SUPERVISOR = 44  # supervisor 전체 재시작 (supervisor exit → watchdog이 재시작)


@dataclass
class RestartRequest:
    """재시작 요청 정보"""
    restart_type: RestartType
    requester_user_id: str
    channel_id: str
    thread_ts: str


class RestartManager:
    """재시작 관리자

    재시작 요청을 받으면 활성 세션을 확인하고,
    필요시 대기 모드로 전환합니다.
    """

    def __init__(
        self,
        get_running_count: Callable[[], int],
        on_restart: Callable[[RestartType], None],
    ):
        """
        Args:
            get_running_count: 현재 실행 중인 세션 수를 반환하는 함수
            on_restart: 재시작을 실행하는 함수 (RestartType을 인자로 받음)
        """
        self._get_running_count = get_running_count
        self._on_restart = on_restart

        # 대기 상태
        self._pending_restart: Optional[RestartRequest] = None
        self._lock = threading.Lock()

    @property
    def is_pending(self) -> bool:
        """재시작 대기 중인지 확인"""
        with self._lock:
            return self._pending_restart is not None

    @property
    def pending_request(self) -> Optional[RestartRequest]:
        """대기 중인 재시작 요청 반환"""
        with self._lock:
            return self._pending_restart

    def request_restart(self, request: RestartRequest) -> bool:
        """재시작 요청 (대기 모드 진입)

        Args:
            request: 재시작 요청 정보

        Returns:
            True if 대기 모드 진입, False if 이미 대기 중
        """
        with self._lock:
            if self._pending_restart is not None:
                logger.warning("이미 재시작 대기 중입니다.")
                return False

            self._pending_restart = request
            logger.info(f"재시작 대기 시작: type={request.restart_type.name}")
            return True

    def cancel_restart(self) -> bool:
        """재시작 대기 취소

        Returns:
            True if 취소됨, False if 대기 중이 아님
        """
        with self._lock:
            if self._pending_restart is None:
                return False

            self._pending_restart = None
            logger.info("재시작 대기 취소됨")
            return True

    def check_and_restart_if_ready(self) -> bool:
        """실행 중인 세션이 없으면 재시작 실행

        Returns:
            True if 재시작 실행됨, False if 아직 세션 있음 또는 대기 중 아님
        """
        with self._lock:
            if self._pending_restart is None:
                return False

            count = self._get_running_count()
            if count > 0:
                logger.debug(f"재시작 대기 중, 실행 중인 세션: {count}개")
                return False

            request = self._pending_restart
            self._pending_restart = None

        logger.info(f"모든 세션 종료 - 재시작 실행: {request.restart_type.name}")
        self._on_restart(request.restart_type)
        return True

    def force_restart(self, restart_type: RestartType) -> None:
        """즉시 재시작 (대기 없이)"""
        with self._lock:
            self._pending_restart = None

        logger.info(f"즉시 재시작: {restart_type.name}")
        self._on_restart(restart_type)
