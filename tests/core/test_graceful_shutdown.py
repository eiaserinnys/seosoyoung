"""graceful shutdown 대기 로직 테스트

SIGTERM / HTTP /shutdown 수신 시 활성 세션 대기 후 종료하는 로직을 검증합니다.
main.py의 _shutdown_with_session_wait 함수와 동등한 로직을 RestartManager로 재현하여 테스트합니다.
"""

import threading
import time
import pytest
from unittest.mock import MagicMock, call

from seosoyoung.slackbot.restart import RestartManager, RestartRequest, RestartType


GRACEFUL_SHUTDOWN_TIMEOUT = 60


def make_shutdown_with_session_wait(manager: RestartManager, restart_type: RestartType):
    """main.py의 _shutdown_with_session_wait 동등 구현 (테스트용)

    실제 함수는 main.py 모듈 레벨 변수(restart_manager)에 의존하므로,
    동일한 로직을 RestartManager 인스턴스를 주입받아 구현합니다.
    """
    _timer_holder = []

    def shutdown_with_session_wait(source: str = "TEST"):
        result = manager.request_system_shutdown(restart_type)
        if result:
            return

        def _force_shutdown():
            manager.force_restart(restart_type)

        timer = threading.Timer(GRACEFUL_SHUTDOWN_TIMEOUT, _force_shutdown)
        timer.daemon = True
        timer.start()
        _timer_holder.append(timer)

    return shutdown_with_session_wait, _timer_holder


class TestShutdownWithNoActiveSessions:
    """활성 세션이 없을 때의 shutdown 동작"""

    def test_sigterm_no_sessions_immediate_restart(self):
        """SIGTERM: 활성 세션 없으면 즉시 종료"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        on_restart.assert_called_once_with(RestartType.RESTART)
        assert manager.is_pending is False

    def test_http_shutdown_no_sessions_immediate_restart(self):
        """HTTP /shutdown: 활성 세션 없으면 즉시 종료"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        on_restart.assert_called_once_with(RestartType.RESTART)


class TestShutdownWithActiveSessions:
    """활성 세션이 있을 때의 shutdown 동작"""

    def test_sigterm_with_sessions_enters_pending(self):
        """SIGTERM: 활성 세션 있으면 pending 모드 진입"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        on_restart.assert_not_called()
        assert manager.is_pending is True

    def test_http_shutdown_with_sessions_enters_pending(self):
        """HTTP /shutdown: 활성 세션 있으면 pending 모드 진입"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 2,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        on_restart.assert_not_called()
        assert manager.is_pending is True

    def test_sigterm_waits_then_restarts_when_session_ends(self):
        """SIGTERM: 세션 종료 시 check_and_restart_if_ready를 통해 재시작"""
        on_restart = MagicMock()
        running_count = [1]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        # 아직 세션 진행 중
        assert manager.is_pending is True
        on_restart.assert_not_called()

        # 세션 종료 시뮬레이션
        running_count[0] = 0
        manager.check_and_restart_if_ready()

        on_restart.assert_called_once_with(RestartType.RESTART)
        assert manager.is_pending is False

    def test_http_shutdown_waits_then_restarts_when_session_ends(self):
        """HTTP /shutdown: 세션 종료 시 check_and_restart_if_ready를 통해 재시작"""
        on_restart = MagicMock()
        running_count = [3]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        assert manager.is_pending is True

        # 세션 하나씩 종료
        running_count[0] = 2
        assert manager.check_and_restart_if_ready() is False

        running_count[0] = 1
        assert manager.check_and_restart_if_ready() is False

        running_count[0] = 0
        assert manager.check_and_restart_if_ready() is True
        on_restart.assert_called_once_with(RestartType.RESTART)

    def test_pending_request_is_system_flagged(self):
        """shutdown 요청으로 등록된 pending은 is_system=True"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        assert manager.pending_request is not None
        assert manager.pending_request.is_system is True

    def test_duplicate_sigterm_does_not_override_pending(self):
        """중복 SIGTERM은 기존 pending 유지"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        shutdown_fn, _ = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")
        first_pending = manager.pending_request

        # 두 번째 SIGTERM (중복)
        shutdown_fn("SIGTERM")
        assert manager.pending_request is first_pending


class TestTimeoutSafetyNet:
    """타임아웃 안전망 동작 테스트 (단축된 타임아웃 사용)"""

    def test_timeout_triggers_force_restart(self):
        """타임아웃 초과 시 강제 종료 실행"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,  # 세션이 영원히 끝나지 않는 상황
            on_restart=on_restart,
        )
        timeout_sec = 0.1  # 테스트용 짧은 타임아웃

        # 직접 타임아웃 타이머 시뮬레이션
        manager.request_system_shutdown(RestartType.RESTART)
        assert manager.is_pending is True

        def _force_shutdown():
            manager.force_restart(RestartType.RESTART)

        timer = threading.Timer(timeout_sec, _force_shutdown)
        timer.daemon = True
        timer.start()

        # 타임아웃 대기
        time.sleep(timeout_sec + 0.05)

        on_restart.assert_called_once_with(RestartType.RESTART)

    def test_no_timeout_if_session_ends_early(self):
        """세션이 타임아웃 전에 끝나면 force_restart 호출 안 됨"""
        on_restart = MagicMock()
        running_count = [1]
        timeout_sec = 0.2

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.RESTART)

        def _force_shutdown():
            manager.force_restart(RestartType.RESTART)

        timer = threading.Timer(timeout_sec, _force_shutdown)
        timer.daemon = True
        timer.start()

        # 타임아웃 전에 세션 종료
        running_count[0] = 0
        manager.check_and_restart_if_ready()

        # 타이머가 발동되기 전에 정상 종료됨
        timer.cancel()

        # check_and_restart_if_ready에 의해 한 번만 호출됨
        on_restart.assert_called_once_with(RestartType.RESTART)
