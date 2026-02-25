"""RestartManager 테스트"""

import pytest
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
        """재시작 요청 등록"""
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
        assert manager.is_pending is True
        assert manager.pending_request == request

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
        """실행 중인 세션이 있을 때"""
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
        # 여전히 대기 중
        assert manager.is_pending is True

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
        """활성 세션이 있으면 pending 모드 진입, on_restart 호출 안 함"""
        on_restart = MagicMock()
        manager = RestartManager(
            get_running_count=lambda: 2,
            on_restart=on_restart,
        )

        result = manager.request_system_shutdown(RestartType.RESTART)

        assert result is False
        on_restart.assert_not_called()
        assert manager.is_pending is True

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
        """pending 상태에서 세션 종료 시 check_and_restart_if_ready 통해 재시작"""
        on_restart = MagicMock()
        running_count = [1]

        manager = RestartManager(
            get_running_count=lambda: running_count[0],
            on_restart=on_restart,
        )

        manager.request_system_shutdown(RestartType.RESTART)
        assert manager.is_pending is True

        # 세션 아직 있음
        assert manager.check_and_restart_if_ready() is False
        on_restart.assert_not_called()

        # 세션 종료
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
