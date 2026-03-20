"""graceful shutdown 대기 로직 테스트

SIGTERM / HTTP /shutdown 수신 시 활성 세션 대기 후 종료하는 로직을 검증합니다.
main.py의 _shutdown_with_session_wait 함수와 동등한 로직을 RestartManager로 재현하여 테스트합니다.
"""

from unittest.mock import MagicMock

from seosoyoung.slackbot.restart import RestartManager, RestartType


def make_shutdown_with_session_wait(manager: RestartManager, restart_type: RestartType):
    """main.py의 _shutdown_with_session_wait 동등 구현 (테스트용)

    실제 함수는 main.py 모듈 레벨 변수(restart_manager)에 의존하므로,
    동일한 로직을 RestartManager 인스턴스를 주입받아 구현합니다.

    타임아웃 안전망은 사용자의 팝업 응답을 무시하고 강제 종료하는 문제를
    일으키므로 제거되었다. 프로세스 관리자가 수명을 관리한다.
    """

    def shutdown_with_session_wait(source: str = "TEST"):
        manager.request_system_shutdown(restart_type)

    return shutdown_with_session_wait


class TestShutdownWithNoActiveSessions:
    """활성 세션이 없을 때의 shutdown 동작"""

    def test_sigterm_no_sessions_immediate_restart(self):
        """SIGTERM: 활성 세션 없으면 즉시 종료"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
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

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        on_restart.assert_called_once_with(RestartType.RESTART)


class TestShutdownWithActiveSessions:
    """활성 세션이 있을 때의 shutdown 동작"""

    def test_sigterm_with_sessions_enters_pending(self):
        """SIGTERM: 활성 세션 있으면 pending_request 등록 (is_pending은 사용자 확인 후 True)"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        on_restart.assert_not_called()
        assert manager.pending_request is not None

    def test_http_shutdown_with_sessions_enters_pending(self):
        """HTTP /shutdown: 활성 세션 있으면 pending_request 등록 (is_pending은 사용자 확인 후 True)"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 2,
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        on_restart.assert_not_called()
        assert manager.pending_request is not None

    def test_sigterm_waits_then_restarts_when_session_ends(self):
        """SIGTERM: 세션 종료 시 check_and_restart_if_ready를 통해 재시작"""
        on_restart = MagicMock()
        running_count = [1]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        # 아직 세션 진행 중 — pending_request 등록됨, is_pending은 사용자 확인 전 False
        assert manager.pending_request is not None
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

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("HTTP /shutdown")

        assert manager.pending_request is not None

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

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
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

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")
        first_pending = manager.pending_request

        # 두 번째 SIGTERM (중복)
        shutdown_fn("SIGTERM")
        assert manager.pending_request is first_pending


class TestNoTimeoutSafetyNet:
    """타임아웃 안전망이 제거되었음을 검증하는 테스트

    봇 내부에서 타임아웃으로 강제 종료하면 사용자의 팝업 응답을 무시하게 되므로,
    shutdown_with_session_wait는 타이머를 설정하지 않는다.
    supervisor가 프로세스 수명을 관리한다.
    """

    def test_pending_sessions_do_not_force_restart(self):
        """활성 세션이 있으면 사용자 응답 없이는 재시작하지 않음"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,  # 세션이 영원히 끝나지 않는 상황
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        # pending_request 등록됨, on_restart는 호출되지 않음
        assert manager.pending_request is not None
        on_restart.assert_not_called()

    def test_only_session_end_triggers_restart(self):
        """세션이 끝나야만 재시작이 실행됨"""
        on_restart = MagicMock()
        running_count = [1]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        shutdown_fn = make_shutdown_with_session_wait(manager, RestartType.RESTART)
        shutdown_fn("SIGTERM")

        # 아직 세션 진행 중 — 재시작 안 됨
        assert manager.check_and_restart_if_ready() is False
        on_restart.assert_not_called()

        # 세션 종료 — 이제야 재시작
        running_count[0] = 0
        assert manager.check_and_restart_if_ready() is True
        on_restart.assert_called_once_with(RestartType.RESTART)
