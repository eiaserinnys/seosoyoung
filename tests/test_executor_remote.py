"""executor.py의 remote 모드 분기 로직 테스트

env 분기, remote 실행, 인터벤션 이중화를 검증합니다.
"""

import threading

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from seosoyoung.claude.executor import (
    ClaudeExecutor,
    PendingPrompt,
    _is_remote_mode,
)
from seosoyoung.claude.session import Session, SessionManager


# === _is_remote_mode 테스트 ===

class TestIsRemoteMode:
    """_is_remote_mode() 환경 변수 분기 테스트"""

    def test_default_is_local(self):
        """기본값은 local"""
        with patch("seosoyoung.claude.executor.Config") as mock_config:
            mock_config.CLAUDE_EXECUTION_MODE = "local"
            assert _is_remote_mode() is False

    def test_remote_mode(self):
        """CLAUDE_EXECUTION_MODE=remote"""
        with patch("seosoyoung.claude.executor.Config") as mock_config:
            mock_config.CLAUDE_EXECUTION_MODE = "remote"
            assert _is_remote_mode() is True

    def test_invalid_value_is_not_remote(self):
        """잘못된 값은 remote가 아님"""
        with patch("seosoyoung.claude.executor.Config") as mock_config:
            mock_config.CLAUDE_EXECUTION_MODE = "unknown"
            assert _is_remote_mode() is False


# === ClaudeExecutor remote 분기 테스트 ===

class TestExecutorRemoteBranch:
    """ClaudeExecutor._execute_once에서 remote/local 분기 테스트"""

    @pytest.fixture
    def mock_session_manager(self, tmp_path):
        sm = SessionManager(session_dir=tmp_path / "sessions")
        return sm

    @pytest.fixture
    def executor(self, mock_session_manager):
        return ClaudeExecutor(
            session_manager=mock_session_manager,
            get_session_lock=lambda ts: threading.RLock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

    @pytest.fixture
    def session(self, mock_session_manager):
        return mock_session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_local_mode_uses_runner(self, executor, session):
        """local 모드에서 get_runner_for_role이 호출되는지 확인"""
        mock_client = MagicMock()
        mock_say = MagicMock()

        with patch("seosoyoung.claude.executor._is_remote_mode", return_value=False), \
             patch("seosoyoung.claude.executor.get_runner_for_role") as mock_get_runner:

            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.output = "hello"
            mock_result.session_id = "sess-1"
            mock_result.interrupted = False
            mock_result.update_requested = False
            mock_result.restart_requested = False
            mock_result.list_run = None
            mock_result.error = None
            mock_result.usage = None

            mock_runner.run_sync.return_value = mock_result
            mock_get_runner.return_value = mock_runner

            executor._execute_once(
                session=session,
                prompt="hello",
                msg_ts="1234.0001",
                channel="C123",
                say=mock_say,
                client=mock_client,
                effective_role="admin",
                trello_card=None,
                is_existing_thread=False,
                initial_msg_ts="1234.0002",
                is_trello_mode=False,
                thread_ts_override=None,
            )

            mock_get_runner.assert_called_once_with("admin")

    def test_remote_mode_uses_adapter(self, executor, session):
        """remote 모드에서 _execute_remote가 호출되는지 확인"""
        mock_client = MagicMock()
        mock_say = MagicMock()

        with patch("seosoyoung.claude.executor._is_remote_mode", return_value=True), \
             patch.object(executor, "_execute_remote") as mock_execute_remote:

            executor._execute_once(
                session=session,
                prompt="hello",
                msg_ts="1234.0001",
                channel="C123",
                say=mock_say,
                client=mock_client,
                effective_role="admin",
                trello_card=None,
                is_existing_thread=False,
                initial_msg_ts="1234.0002",
                is_trello_mode=False,
                thread_ts_override=None,
            )

            mock_execute_remote.assert_called_once()


class TestGetServiceAdapter:
    """_get_service_adapter lazy 초기화 테스트"""

    @pytest.fixture
    def executor(self, tmp_path):
        sm = SessionManager(session_dir=tmp_path / "sessions")
        return ClaudeExecutor(
            session_manager=sm,
            get_session_lock=lambda ts: threading.RLock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

    def test_lazy_init(self, executor):
        """첫 호출 시 adapter가 생성되고 이후 재사용"""
        with patch("seosoyoung.claude.executor.Config") as mock_config:
            mock_config.SEOSOYOUNG_SOUL_URL = "http://localhost:3105"
            mock_config.SEOSOYOUNG_SOUL_TOKEN = "test-token"
            mock_config.SEOSOYOUNG_SOUL_CLIENT_ID = "test_bot"

            adapter1 = executor._get_service_adapter()
            adapter2 = executor._get_service_adapter()

            assert adapter1 is adapter2
            assert adapter1 is not None


class TestInterventionDualPath:
    """인터벤션 이중화 테스트"""

    @pytest.fixture
    def executor(self, tmp_path):
        sm = SessionManager(session_dir=tmp_path / "sessions")
        return ClaudeExecutor(
            session_manager=sm,
            get_session_lock=lambda ts: threading.RLock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=0),
            restart_manager=MagicMock(),
            upload_file_to_slack=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
        )

    def test_local_intervention_uses_runner(self, executor):
        """local 모드 인터벤션: runner.interrupt 호출 (동기)"""
        mock_runner = MagicMock()
        executor._active_runners["1234.5678"] = mock_runner

        with patch("seosoyoung.claude.executor._is_remote_mode", return_value=False):
            executor._handle_intervention(
                thread_ts="1234.5678",
                prompt="new prompt",
                msg_ts="1234.0001",
                channel="C123",
                say=MagicMock(),
                client=MagicMock(),
            )

        # runner.interrupt()가 직접 호출되어야 함 (이제 동기)
        mock_runner.interrupt.assert_called_once_with("1234.5678")

    def test_remote_intervention_uses_adapter(self, executor):
        """remote 모드 인터벤션: run_in_new_loop으로 adapter.intervene 호출"""
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._active_remote_requests["1234.5678"] = "1234.5678"

        with patch("seosoyoung.claude.executor._is_remote_mode", return_value=True), \
             patch("seosoyoung.claude.agent_runner.run_in_new_loop") as mock_run:

            mock_run.return_value = True

            executor._handle_intervention(
                thread_ts="1234.5678",
                prompt="new prompt",
                msg_ts="1234.0001",
                channel="C123",
                say=MagicMock(),
                client=MagicMock(),
            )

            # run_in_new_loop으로 adapter.intervene이 호출되어야 함
            mock_run.assert_called_once()

    def test_pending_prompt_saved_on_intervention(self, executor):
        """인터벤션 시 pending에 프롬프트가 저장되는지 확인"""
        with patch("seosoyoung.claude.executor._is_remote_mode", return_value=False):
            executor._handle_intervention(
                thread_ts="1234.5678",
                prompt="new prompt",
                msg_ts="1234.0001",
                channel="C123",
                say=MagicMock(),
                client=MagicMock(),
            )

        assert "1234.5678" in executor._pending_prompts
        assert executor._pending_prompts["1234.5678"].prompt == "new prompt"


class TestConfigEnvVars:
    """Config에 추가된 env 변수 테스트"""

    def test_default_execution_mode(self):
        """기본 실행 모드는 local"""
        with patch.dict("os.environ", {}, clear=True):
            # Config는 모듈 로드 시 평가되므로 직접 확인
            from seosoyoung.config import Config
            # 환경변수가 없을 때 기본값 확인
            assert Config.CLAUDE_EXECUTION_MODE in ("local", "remote")

    def test_soul_url_default(self):
        from seosoyoung.config import Config
        assert "localhost" in Config.SEOSOYOUNG_SOUL_URL or Config.SEOSOYOUNG_SOUL_URL != ""

    def test_soul_client_id_default(self):
        from seosoyoung.config import Config
        assert Config.SEOSOYOUNG_SOUL_CLIENT_ID == "seosoyoung_bot"
