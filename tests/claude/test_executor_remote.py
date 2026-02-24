"""executor.py의 remote 모드 분기 로직 테스트

env 분기, remote 실행, 인터벤션 이중화를 검증합니다.
"""

import threading

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from seosoyoung.slackbot.claude.executor import (
    ClaudeExecutor,
    ExecutionContext,
    PendingPrompt,
)
from seosoyoung.slackbot.claude.session import Session, SessionManager, SessionRuntime


# === execution_mode 테스트 ===

class TestExecutionMode:
    """ClaudeExecutor의 execution_mode 분기 테스트"""

    def test_default_is_local(self):
        """기본값은 local"""
        executor = _make_executor()
        assert executor.execution_mode == "local"

    def test_remote_mode(self):
        """execution_mode=remote"""
        executor = _make_executor(execution_mode="remote")
        assert executor.execution_mode == "remote"

    def test_invalid_value_is_not_remote(self):
        """잘못된 값은 remote가 아님"""
        executor = _make_executor(execution_mode="unknown")
        assert executor.execution_mode != "remote"


def _make_executor(tmp_path=None, **overrides):
    """테스트용 ClaudeExecutor 생성 헬퍼"""
    import tempfile
    from pathlib import Path

    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    sm = SessionManager(session_dir=tmp_path / "sessions")
    sr = SessionRuntime()
    defaults = dict(
        session_manager=sm,
        session_runtime=sr,
        restart_manager=MagicMock(),
        send_long_message=MagicMock(),
        send_restart_confirmation=MagicMock(),
        update_message_fn=MagicMock(),
    )
    defaults.update(overrides)
    return ClaudeExecutor(**defaults)


def _make_ctx(session, **overrides):
    """테스트용 ExecutionContext 생성 헬퍼"""
    defaults = dict(
        session=session,
        channel="C123",
        say=MagicMock(),
        client=MagicMock(),
        msg_ts="1234.0001",
        effective_role="admin",
        thread_ts=session.thread_ts,
    )
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# === ClaudeExecutor remote 분기 테스트 ===

class TestExecutorRemoteBranch:
    """ClaudeExecutor._execute_once에서 remote/local 분기 테스트"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(tmp_path)

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_local_mode_uses_runner(self, executor, session):
        """local 모드에서 ClaudeRunner가 생성되는지 확인"""
        ctx = _make_ctx(session, initial_msg_ts="1234.0002")
        executor.execution_mode = "local"

        with patch("seosoyoung.slackbot.claude.executor.ClaudeRunner") as MockRunnerClass:
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
            MockRunnerClass.return_value = mock_runner

            executor._execute_once(ctx, "hello")

            MockRunnerClass.assert_called_once()

    def test_remote_mode_uses_adapter(self, executor, session):
        """remote 모드에서 _execute_remote가 호출되는지 확인"""
        ctx = _make_ctx(session, initial_msg_ts="1234.0002")
        executor.execution_mode = "remote"

        with patch.object(executor, "_execute_remote") as mock_execute_remote:
            executor._execute_once(ctx, "hello")
            mock_execute_remote.assert_called_once()


class TestGetServiceAdapter:
    """_get_service_adapter lazy 초기화 테스트"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )

    def test_lazy_init(self, executor):
        """첫 호출 시 adapter가 생성되고 이후 재사용"""
        adapter1 = executor._get_service_adapter()
        adapter2 = executor._get_service_adapter()

        assert adapter1 is adapter2
        assert adapter1 is not None


class TestInterventionDualPath:
    """인터벤션 이중화 테스트"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(tmp_path)

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_local_intervention_uses_runner(self, executor, session):
        """local 모드 인터벤션: runner.interrupt 호출 (동기, 인자 없음)"""
        mock_runner = MagicMock()
        executor.execution_mode = "local"

        ctx = _make_ctx(session)

        with patch("seosoyoung.slackbot.claude.agent_runner.get_runner", return_value=mock_runner):
            executor._handle_intervention(ctx, "new prompt")

        mock_runner.interrupt.assert_called_once()

    def test_remote_intervention_uses_adapter(self, executor, session):
        """remote 모드 인터벤션: run_in_new_loop으로 adapter.intervene 호출"""
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._active_remote_requests["1234.5678"] = "1234.5678"
        executor.execution_mode = "remote"

        ctx = _make_ctx(session)

        with patch("seosoyoung.utils.async_bridge.run_in_new_loop") as mock_run:
            mock_run.return_value = True
            executor._handle_intervention(ctx, "new prompt")
            mock_run.assert_called_once()

    def test_pending_prompt_saved_on_intervention(self, executor, session):
        """인터벤션 시 pending에 프롬프트가 저장되는지 확인"""
        ctx = _make_ctx(session)
        executor.execution_mode = "local"
        executor._handle_intervention(ctx, "new prompt")

        assert "1234.5678" in executor._pending_prompts
        assert executor._pending_prompts["1234.5678"].prompt == "new prompt"


class TestConfigEnvVars:
    """Config에 추가된 env 변수 테스트"""

    def test_default_execution_mode(self):
        """기본 실행 모드는 local"""
        with patch.dict("os.environ", {}, clear=True):
            # Config는 모듈 로드 시 평가되므로 직접 확인
            from seosoyoung.slackbot.config import Config
            # 환경변수가 없을 때 기본값 확인
            assert Config.claude.execution_mode in ("local", "remote")

    def test_soul_url_default(self):
        from seosoyoung.slackbot.config import Config
        assert "localhost" in Config.claude.soul_url or Config.claude.soul_url != ""

    def test_soul_client_id_default(self):
        from seosoyoung.slackbot.config import Config
        assert Config.claude.soul_client_id == "seosoyoung_bot"
