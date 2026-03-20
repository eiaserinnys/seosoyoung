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
    UPDATE = 42   # git pull 후 재시작 (프로세스 관리자가 git pull 수행)
    RESTART = 43  # 봇 프로세스만 재시작
    RESTART_SUPERVISOR = 44  # 프로세스 관리자 전체 재시작


@dataclass
class RestartRequest:
    """재시작 요청 정보"""
    restart_type: RestartType
    requester_user_id: str = ""
    channel_id: str = ""
    thread_ts: str = ""
    is_system: bool = False  # True이면 시스템 내부 shutdown (SIGTERM, HTTP /shutdown 등)


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
        self._user_confirmed: bool = False
        self._lock = threading.Lock()

    @property
    def is_pending(self) -> bool:
        """재시작 대기 중이며 사용자가 확인한 상태인지 확인.

        팝업이 떴더라도 사용자가 '세션 완료 후 종료' 버튼을 누르기 전까지는
        False를 반환하여 대화를 차단하지 않는다.
        """
        with self._lock:
            return self._pending_restart is not None and self._user_confirmed

    @property
    def is_shutdown_requested(self) -> bool:
        """사용자 확인 여부와 무관하게 종료/재시작 요청이 등록되어 있는지 확인.

        세션 종료 콜백에서 자동 재시작 트리거 여부를 판단할 때 사용한다.
        새 대화 차단 여부는 is_pending을 사용한다.

        - is_shutdown_requested: pending 등록됨 → 세션 0이 되면 재시작 실행
        - is_pending: pending + user_confirmed → 신규 대화 차단
        """
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
            self._user_confirmed = False
            logger.info(f"재시작 대기 시작: type={request.restart_type.name}")
            return True

    def request_system_shutdown(self, restart_type: RestartType) -> bool:
        """시스템 수준의 종료 요청 (SIGTERM, HTTP /shutdown 등)

        사용자 정보 없이 pending 등록합니다.
        활성 세션이 없으면 즉시 종료, 있으면 세션 종료 후 자동 종료됩니다.

        Args:
            restart_type: 재시작 유형

        Returns:
            True if 즉시 종료 실행, False if 세션 대기 모드 진입
        """
        count = self._get_running_count()
        if count == 0:
            logger.info(f"활성 세션 없음 — 즉시 종료: {restart_type.name}")
            self._on_restart(restart_type)
            return True

        logger.info(
            f"활성 세션 {count}개 감지 — 종료 대기 모드 진입: {restart_type.name}"
        )
        with self._lock:
            if self._pending_restart is not None:
                logger.warning("이미 재시작 대기 중 — 기존 요청 유지")
                return False
            self._pending_restart = RestartRequest(
                restart_type=restart_type,
                is_system=True,
            )
            self._user_confirmed = False
        return False

    def confirm_shutdown(self) -> None:
        """사용자가 '세션 완료 후 종료' 버튼을 클릭했음을 기록.

        이 시점부터 is_pending이 True가 되어 새 대화가 차단된다.
        """
        with self._lock:
            self._user_confirmed = True
        logger.info("사용자 종료 확인 — 이후 신규 대화 차단")

    def cancel_restart(self) -> bool:
        """재시작 대기 취소

        Returns:
            True if 취소됨, False if 대기 중이 아님
        """
        with self._lock:
            if self._pending_restart is None:
                return False

            self._pending_restart = None
            self._user_confirmed = False
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
            self._user_confirmed = False

        logger.info(f"즉시 재시작: {restart_type.name}")
        self._on_restart(restart_type)
