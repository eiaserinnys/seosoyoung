"""RestartManager 테스트"""

import pytest
from unittest import mock
from unittest.mock import MagicMock, call

from seosoyoung.slackbot.restart import RestartManager, RestartRequest, RestartType


class TestRestartType:
    """RestartType enum 테스트"""

    def test_restart_type_values(self):
        """exit code 값 확인"""
        assert RestartType.UPDATE.value == 42
        assert RestartType.RESTART.value == 43
        assert RestartType.RESTART_SUPERVISOR.value == 44


class TestRestartRequest:
    """RestartRequest 데이터 클래스 테스트"""

    def test_restart_request_creation(self):
        """요청 생성"""
        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )

        assert request.restart_type == RestartType.UPDATE
        assert request.requester_user_id == "U12345"
        assert request.channel_id == "C12345"
        assert request.thread_ts == "1234567890.123456"


class TestRestartManager:
    """RestartManager 테스트"""

    def test_initial_state(self):
        """초기 상태는 대기 중이 아님"""
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=MagicMock()
        )

        assert manager.is_pending is False
        assert manager.pending_request is None

    def test_request_restart(self):
        """재시작 요청 등록: pending_request는 설정되지만 is_pending은 사용자 확인 전까지 False"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock()
        )

        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )

        result = manager.request_restart(request)

        assert result is True
        # pending_request는 등록됨
        assert manager.pending_request == request
        # is_pending은 사용자 확인 전까지 False
        assert manager.is_pending is False

    def test_request_restart_already_pending(self):
        """이미 대기 중일 때 중복 요청"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock()
        )

        request1 = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        request2 = RestartRequest(
            restart_type=RestartType.RESTART,
            requester_user_id="U67890",
            channel_id="C67890",
            thread_ts="9876543210.654321"
        )

        manager.request_restart(request1)
        result = manager.request_restart(request2)

        assert result is False
        # 첫 번째 요청 유지
        assert manager.pending_request == request1

    def test_cancel_restart(self):
        """재시작 대기 취소"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock()
        )

        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        manager.request_restart(request)
        manager.confirm_shutdown()

        result = manager.cancel_restart()

        assert result is True
        assert manager.is_pending is False
        assert manager.pending_request is None

    def test_cancel_restart_not_pending(self):
        """대기 중이 아닐 때 취소 시도"""
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=MagicMock()
        )

        result = manager.cancel_restart()

        assert result is False

    def test_check_and_restart_not_pending(self):
        """대기 중이 아닐 때 check 호출"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart
        )

        result = manager.check_and_restart_if_ready()

        assert result is False
        on_restart.assert_not_called()

    def test_check_and_restart_sessions_running(self):
        """실행 중인 세션이 있을 때: is_pending 여부와 무관하게 재시작 보류"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 2,
            on_restart=on_restart
        )

        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        manager.request_restart(request)

        result = manager.check_and_restart_if_ready()

        assert result is False
        on_restart.assert_not_called()
        # pending_request는 여전히 등록된 상태
        assert manager.pending_request is not None

    def test_check_and_restart_no_sessions(self):
        """실행 중인 세션이 없을 때 재시작"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart
        )

        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        manager.request_restart(request)

        result = manager.check_and_restart_if_ready()

        assert result is True
        on_restart.assert_called_once_with(RestartType.UPDATE)
        # 대기 상태 해제
        assert manager.is_pending is False

    def test_check_and_restart_sessions_become_zero(self):
        """세션이 0이 되었을 때 재시작"""
        running_count = [2]  # mutable로 감싸서 변경 가능하게

        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart
        )

        request = RestartRequest(
            restart_type=RestartType.RESTART,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        manager.request_restart(request)

        # 아직 세션 2개
        assert manager.check_and_restart_if_ready() is False

        # 세션 1개로 감소
        running_count[0] = 1
        assert manager.check_and_restart_if_ready() is False

        # 세션 0개
        running_count[0] = 0
        assert manager.check_and_restart_if_ready() is True
        on_restart.assert_called_once_with(RestartType.RESTART)

    def test_force_restart(self):
        """즉시 재시작"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 5,  # 세션이 있어도
            on_restart=on_restart
        )

        # 대기 중인 요청이 있어도
        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456"
        )
        manager.request_restart(request)

        # 강제 재시작
        manager.force_restart(RestartType.RESTART)

        on_restart.assert_called_once_with(RestartType.RESTART)
        # 대기 상태 해제
        assert manager.is_pending is False

    def test_force_restart_without_pending(self):
        """대기 중이 아닐 때 강제 재시작"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart
        )

        manager.force_restart(RestartType.UPDATE)

        on_restart.assert_called_once_with(RestartType.UPDATE)


class TestConfirmShutdown:
    """confirm_shutdown — 사용자 확인 후 대화 차단 활성화 테스트"""

    def test_is_pending_false_before_confirm(self):
        """confirm_shutdown 호출 전에는 is_pending이 False"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock(),
        )
        manager.request_system_shutdown(RestartType.RESTART)

        assert manager.is_pending is False

    def test_is_pending_true_after_confirm(self):
        """confirm_shutdown 호출 후 is_pending이 True"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock(),
        )
        manager.request_system_shutdown(RestartType.RESTART)
        manager.confirm_shutdown()

        assert manager.is_pending is True

    def test_confirm_without_pending_has_no_effect(self):
        """pending 없이 confirm_shutdown 호출해도 is_pending은 False 유지"""
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=MagicMock(),
        )

        manager.confirm_shutdown()

        assert manager.is_pending is False

    def test_cancel_after_confirm_resets_state(self):
        """confirm_shutdown 후 cancel_restart 호출 시 모든 상태 초기화"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock(),
        )
        manager.request_system_shutdown(RestartType.RESTART)
        manager.confirm_shutdown()
        assert manager.is_pending is True

        manager.cancel_restart()

        assert manager.is_pending is False
        assert manager.pending_request is None

    def test_force_restart_after_confirm_resets_state(self):
        """confirm_shutdown 후 force_restart 호출 시 상태 초기화"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )
        manager.request_system_shutdown(RestartType.RESTART)
        manager.confirm_shutdown()

        manager.force_restart(RestartType.UPDATE)

        assert manager.is_pending is False
        on_restart.assert_called_once_with(RestartType.UPDATE)

    def test_check_and_restart_works_regardless_of_confirm(self):
        """confirm_shutdown 여부와 무관하게 check_and_restart_if_ready는 pending_request만 본다"""
        on_restart = MagicMock()
        running_count = [1]
        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )
        manager.request_system_shutdown(RestartType.RESTART)
        # confirm_shutdown 없이도 세션이 0이 되면 자동 재시작
        assert manager.is_pending is False

        running_count[0] = 0
        assert manager.check_and_restart_if_ready() is True
        on_restart.assert_called_once_with(RestartType.RESTART)

    def test_request_restart_resets_confirmed_flag(self):
        """새 request_restart 호출 시 _user_confirmed 초기화"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock(),
        )
        request1 = RestartRequest(restart_type=RestartType.UPDATE, requester_user_id="U1")
        manager.request_restart(request1)
        manager.confirm_shutdown()
        assert manager.is_pending is True

        # 취소 후 새 요청
        manager.cancel_restart()
        request2 = RestartRequest(restart_type=RestartType.RESTART, requester_user_id="U2")
        manager.request_restart(request2)

        # confirm_shutdown 없이는 다시 False
        assert manager.is_pending is False

    def test_request_system_shutdown_resets_confirmed_flag(self):
        """새 request_system_shutdown 호출 시 _user_confirmed 초기화"""
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=MagicMock(),
        )
        manager.request_system_shutdown(RestartType.RESTART)
        manager.confirm_shutdown()
        manager.cancel_restart()

        manager.request_system_shutdown(RestartType.UPDATE)

        # confirm_shutdown 없이는 False
        assert manager.is_pending is False


class TestRequestSystemShutdown:
    """request_system_shutdown 테스트 — SIGTERM/HTTP shutdown 경로 대기 로직"""

    def test_no_active_sessions_calls_on_restart_immediately(self):
        """활성 세션이 없으면 즉시 on_restart 호출"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 0,
            on_restart=on_restart,
        )

        result = manager.request_system_shutdown(RestartType.RESTART)

        assert result is True
        on_restart.assert_called_once_with(RestartType.RESTART)
        assert manager.is_pending is False

    def test_active_sessions_enters_pending_mode(self):
        """활성 세션이 있으면 pending_request가 등록되지만 is_pending은 확인 전 False"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 2,
            on_restart=on_restart,
        )

        result = manager.request_system_shutdown(RestartType.RESTART)

        assert result is False
        on_restart.assert_not_called()
        # pending_request는 등록됨
        assert manager.pending_request is not None
        # is_pending은 사용자 확인 전 False
        assert manager.is_pending is False

    def test_pending_is_system_flagged(self):
        """pending 요청에 is_system=True 플래그가 설정됨"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.RESTART)

        assert manager.pending_request is not None
        assert manager.pending_request.is_system is True
        assert manager.pending_request.restart_type == RestartType.RESTART

    def test_session_completion_triggers_restart(self):
        """pending 상태에서 세션 종료 시 check_and_restart_if_ready 통해 재시작 (confirm 불필요)"""
        on_restart = MagicMock()
        running_count = [1]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.RESTART)
        # is_pending은 False (confirm 안 했으므로), pending_request는 등록됨
        assert manager.is_pending is False
        assert manager.pending_request is not None

        # 세션 아직 있음
        assert manager.check_and_restart_if_ready() is False
        on_restart.assert_not_called()

        # 세션 종료 — confirm 없이도 자동 재시작
        running_count[0] = 0
        assert manager.check_and_restart_if_ready() is True
        on_restart.assert_called_once_with(RestartType.RESTART)

    def test_already_pending_system_shutdown_not_overridden(self):
        """이미 pending 상태에서 중복 request_system_shutdown은 무시됨"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 1,
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.RESTART)
        first_pending = manager.pending_request

        result = manager.request_system_shutdown(RestartType.UPDATE)

        assert result is False
        # 최초 요청 유지
        assert manager.pending_request is first_pending

    def test_restart_type_preserved_in_pending(self):
        """pending 요청의 restart_type이 올바르게 저장됨"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 3,
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.UPDATE)

        assert manager.pending_request.restart_type == RestartType.UPDATE


class TestRestartRequestDefaults:
    """RestartRequest 기본값 및 is_system 필드 테스트"""

    def test_system_request_has_empty_user_fields(self):
        """시스템 요청은 사용자 필드가 빈 문자열"""
        request = RestartRequest(restart_type=RestartType.RESTART, is_system=True)

        assert request.requester_user_id == ""
        assert request.channel_id == ""
        assert request.thread_ts == ""
        assert request.is_system is True

    def test_user_request_is_system_false_by_default(self):
        """일반 사용자 요청의 is_system 기본값은 False"""
        request = RestartRequest(
            restart_type=RestartType.UPDATE,
            requester_user_id="U12345",
            channel_id="C12345",
            thread_ts="1234567890.123456",
        )

        assert request.is_system is False


class TestSessionShutdownTrigger:
    """_check_restart_on_session_stop 콜백 동작 검증

    main.py를 import하면 슬랙 초기화가 실행되므로,
    RestartManager를 직접 구성하여 콜백 패턴을 재현한다.
    """

    def _make_callback(self, restart_manager):
        """main.py의 _check_restart_on_session_stop과 동일한 콜백 구성"""
        def callback():
            if restart_manager.is_shutdown_requested:
                restart_manager.check_and_restart_if_ready()
        return callback

    def test_system_shutdown_pending_session_0_triggers_restart(self):
        """system shutdown pending 상태에서 세션이 0이 되면 콜백으로 재시작 트리거"""
        on_restart = mock.Mock()
        running_count = [1]
        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )
        # 세션이 있는 상태에서 pending 등록
        manager.request_system_shutdown(RestartType.UPDATE)
        assert manager.is_shutdown_requested is True
        on_restart.assert_not_called()

        # 세션 종료 → 콜백 호출
        running_count[0] = 0
        callback = self._make_callback(manager)
        callback()

        on_restart.assert_called_once_with(RestartType.UPDATE)

    def test_no_confirm_session_0_allows_new_session(self):
        """버튼 미클릭(user_confirmed=False) 상태 → is_pending=False → 신규 대화 허용"""
        # 세션이 1개 있는 상태에서 pending 등록
        manager = RestartManager(get_running_count=lambda: 1, on_restart=mock.Mock())
        manager.request_system_shutdown(RestartType.UPDATE)

        # is_pending은 False (신규 대화 게이트 통과)
        assert manager.is_pending is False
        # is_shutdown_requested는 True (재시작 트리거 통과)
        assert manager.is_shutdown_requested is True

    def test_confirm_shutdown_blocks_new_session(self):
        """confirm_shutdown 후 → is_pending=True → 신규 대화 차단"""
        manager = RestartManager(get_running_count=lambda: 1, on_restart=mock.Mock())
        manager.request_system_shutdown(RestartType.UPDATE)
        manager.confirm_shutdown()

        assert manager.is_pending is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
