"""Phase 4 통합 테스트 — remote 모드 전체 흐름 검증

executor → soul (mock) → SSE → 결과 처리까지의 end-to-end 시나리오를 검증합니다.

테스트 시나리오:
1. 기본 흐름: 멘션 → soul 위임 → SSE 스트리밍 → 응답
2. 인터벤션: 실행 중 스레드 답글 → session_id 기반 interrupt + 재실행
3. 역할별 도구: admin vs viewer 도구 제한
4. 디버그 이벤트: rate_limit 경고 → 슬랙 디버그 채널 전달
5. 컴팩션: compact 이벤트 → SSE 전파 + 봇 정상 처리
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from seosoyoung.slackbot.claude.executor import ClaudeExecutor
from seosoyoung.slackbot.claude.engine_types import ClaudeResult
from seosoyoung.slackbot.claude.intervention import PendingPrompt
from seosoyoung.slackbot.claude.session import SessionManager, SessionRuntime
from seosoyoung.slackbot.presentation.types import PresentationContext


# === 헬퍼 ===

def _make_executor(tmp_path=None, **overrides):
    """테스트용 ClaudeExecutor 생성"""
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


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성"""
    defaults = dict(
        channel="C123",
        thread_ts="1234.5678",
        msg_ts="1234.0001",
        say=MagicMock(),
        client=MagicMock(),
        effective_role="admin",
        session_id="sess-001",
    )
    defaults.update(overrides)
    return PresentationContext(**defaults)


def _noop_progress(text):
    pass


async def _noop_compact(trigger, message):
    pass


# === 1. 기본 흐름 테스트 ===

class TestIntegrationBasicFlow:
    """멘션 → soul 위임 → SSE → 스레드 응답"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_basic_remote_flow(self, executor, session):
        """remote 모드: execute → adapter.execute → ClaudeResult → process_result"""
        pctx = _make_pctx()
        mock_result = ClaudeResult(
            success=True,
            output="안녕하세요, 서소영이옵니다.",
            session_id="sess-remote-001",
        )

        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter

        with patch("seosoyoung.slackbot.claude.executor.run_in_new_loop", return_value=mock_result):
            executor._execute_once(
                "1234.5678", "안녕", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="admin",
                user_message="안녕",
                on_result=None,
            )

        # session_id가 세션 매니저에 기록되었는지 확인
        session_data = executor.session_manager.get("1234.5678")
        assert session_data.session_id == "sess-remote-001"

    def test_basic_flow_with_on_result_callback(self, executor, session):
        """on_result 콜백이 올바르게 호출되는지 확인"""
        pctx = _make_pctx()
        mock_result = ClaudeResult(
            success=True,
            output="결과물",
            session_id="sess-002",
        )

        on_result = MagicMock()
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter

        with patch("seosoyoung.slackbot.claude.executor.run_in_new_loop", return_value=mock_result):
            executor._execute_once(
                "1234.5678", "hello", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="admin",
                user_message="사용자 원본",
                on_result=on_result,
            )

        on_result.assert_called_once_with(mock_result, "1234.5678", "사용자 원본")

    def test_progress_callback_reaches_adapter(self, executor, session):
        """on_progress 콜백이 adapter.execute에 전달되는지 확인"""
        pctx = _make_pctx()
        captured_kwargs = {}

        async def mock_execute(**kwargs):
            captured_kwargs.update(kwargs)
            return ClaudeResult(success=True, output="done", session_id="sess-p")

        mock_adapter = MagicMock()
        mock_adapter.execute = mock_execute

        with patch.object(executor, "_get_service_adapter", return_value=mock_adapter):
            executor._execute_remote(
                "1234.5678", "hello",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                user_message=None,
                on_result=None,
            )

        assert "on_progress" in captured_kwargs
        assert captured_kwargs["on_progress"] is _noop_progress


# === 2. 인터벤션 테스트 ===

class TestIntegrationIntervention:
    """실행 중 스레드 답글 → session_id 매핑 → interrupt + 재실행"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_session_id_registered_during_execution(self, executor, session):
        """실행 중 session_id가 on_session 콜백을 통해 등록되는지 확인"""
        pctx = _make_pctx()

        # adapter.execute가 on_session 콜백을 호출하도록 mock
        captured_on_session = None

        async def mock_execute(**kwargs):
            nonlocal captured_on_session
            captured_on_session = kwargs.get("on_session")
            # session 콜백 호출 시뮬레이션
            if captured_on_session:
                await captured_on_session("sess-live-001")
            return ClaudeResult(success=True, output="done", session_id="sess-live-001")

        mock_adapter = MagicMock()
        mock_adapter.execute = mock_execute
        executor._service_adapter = mock_adapter

        executor._execute_remote(
            "1234.5678", "hello",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            session_id=None,
            user_message=None,
            on_result=None,
        )

        # 실행 완료 후에는 session_id 매핑이 해제됨 (정상 동작)
        assert executor._get_session_id("1234.5678") is None

    def test_intervention_uses_session_based_api(self, executor, session):
        """session_id 확보 후 인터벤션은 session 기반 API를 사용"""
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._active_remote_requests["1234.5678"] = "1234.5678"
        executor._register_session_id("1234.5678", "sess-abc")

        pctx = _make_pctx()

        with patch("seosoyoung.utils.async_bridge.run_in_new_loop") as mock_run:
            mock_run.return_value = True
            executor._handle_intervention(
                "1234.5678", "추가 지시", "1234.0002",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                role="admin",
                user_message=None,
                on_result=None,
                session_id="sess-abc",
            )
            # run_in_new_loop으로 adapter.intervene_by_session이 호출됨
            mock_run.assert_called_once()

    def test_intervention_buffered_before_session_id(self, executor, session):
        """session_id 미확보 상태에서 인터벤션은 버퍼에 보관"""
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._active_remote_requests["1234.5678"] = "1234.5678"
        # session_id는 아직 등록 안 됨

        pctx = _make_pctx()

        executor._handle_intervention(
            "1234.5678", "빨리 해줘", "1234.0002",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            role="admin",
            user_message=None,
            on_result=None,
            session_id=None,
        )

        # 버퍼에 보관되었는지 확인
        assert "1234.5678" in executor._pending_session_interventions
        assert len(executor._pending_session_interventions["1234.5678"]) == 1

    def test_buffered_interventions_flushed_on_session_register(self, executor, session):
        """session_id 등록 시 버퍼된 인터벤션이 flush"""
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter

        # 버퍼에 인터벤션 추가
        executor._pending_session_interventions["1234.5678"] = [
            ("추가 지시1", "intervention"),
            ("추가 지시2", "intervention"),
        ]

        with patch("seosoyoung.utils.async_bridge.run_in_new_loop") as mock_run:
            mock_run.return_value = True
            executor._register_session_id("1234.5678", "sess-new")

            # 2개의 버퍼된 인터벤션이 flush됨
            assert mock_run.call_count == 2

        # 버퍼가 비어졌는지 확인
        assert "1234.5678" not in executor._pending_session_interventions

    def test_pending_consumed_after_execution(self, executor, session):
        """실행 완료 후 pending이 있으면 이어서 실행"""
        pctx = _make_pctx()

        call_count = 0

        def mock_execute_once(thread_ts, prompt, msg_ts, **kwargs):
            nonlocal call_count
            call_count += 1

        with patch.object(executor, "_execute_once", side_effect=mock_execute_once):
            # pending에 프롬프트 저장
            executor._intervention.save_pending("1234.5678", PendingPrompt(
                prompt="후속 질문",
                msg_ts="1234.0002",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
            ))

            executor._run_with_lock(
                "1234.5678", "첫 질문", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="admin",
                user_message=None,
                on_result=None,
            )

        # 첫 실행 + pending 이어서 실행 = 2회
        assert call_count == 2


# === 3. 역할별 도구 테스트 ===

class TestIntegrationRoleTools:
    """admin vs viewer 역할별 도구 제한"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            role_tools={
                "admin": None,
                "viewer": ["Read", "Glob", "Grep"],
            },
        )

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_admin_gets_full_tools(self, executor, session):
        """admin은 모든 도구 허용 (allowed_tools=None, disallowed_tools=None, use_mcp=True)"""
        pctx = _make_pctx()

        with patch.object(executor, "_execute_remote") as mock_remote:
            executor._execute_once(
                "1234.5678", "hello", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="admin",
                user_message=None,
                on_result=None,
            )

            kwargs = mock_remote.call_args.kwargs
            assert kwargs["allowed_tools"] is None  # 무제한
            assert kwargs["disallowed_tools"] is None
            assert kwargs["use_mcp"] is True

    def test_viewer_gets_restricted_tools(self, executor, session):
        """viewer는 Read/Glob/Grep만 허용, 위험 도구 차단, MCP 비활성"""
        pctx = _make_pctx()

        with patch.object(executor, "_execute_remote") as mock_remote:
            executor._execute_once(
                "1234.5678", "hello", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="viewer",
                user_message=None,
                on_result=None,
            )

            kwargs = mock_remote.call_args.kwargs
            assert kwargs["allowed_tools"] == ["Read", "Glob", "Grep"]
            assert "Write" in kwargs["disallowed_tools"]
            assert "Bash" in kwargs["disallowed_tools"]
            assert "Edit" in kwargs["disallowed_tools"]
            assert kwargs["use_mcp"] is False

    def test_unknown_role_defaults_to_viewer(self, executor, session):
        """알 수 없는 role은 viewer 권한으로 폴백"""
        pctx = _make_pctx()

        with patch.object(executor, "_execute_remote") as mock_remote:
            executor._execute_once(
                "1234.5678", "hello", "1234.0001",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                role="unknown_role",
                user_message=None,
                on_result=None,
            )

            kwargs = mock_remote.call_args.kwargs
            assert kwargs["allowed_tools"] == ["Read", "Glob", "Grep"]


# === 4. 디버그 이벤트 테스트 ===

class TestIntegrationDebugEvents:
    """rate_limit 등 디버그 이벤트가 슬랙에 전달"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_debug_event_forwarded_to_slack(self, executor, session):
        """on_debug 콜백이 presentation.client.chat_postMessage를 호출"""
        pctx = _make_pctx()
        captured_on_debug = None

        async def mock_execute(**kwargs):
            nonlocal captured_on_debug
            captured_on_debug = kwargs.get("on_debug")
            # 디버그 콜백 직접 호출
            if captured_on_debug:
                await captured_on_debug("⚠️ rate_limit: 80% 사용")
            return ClaudeResult(success=True, output="done", session_id="sess-d")

        mock_adapter = MagicMock()
        mock_adapter.execute = mock_execute

        with patch.object(executor, "_get_service_adapter", return_value=mock_adapter):
            executor._execute_remote(
                "1234.5678", "hello",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                user_message=None,
                on_result=None,
            )

        # chat_postMessage로 디버그 메시지가 전달되었는지 확인
        pctx.client.chat_postMessage.assert_called_once_with(
            channel="C123",
            thread_ts="1234.5678",
            text="⚠️ rate_limit: 80% 사용",
        )

    def test_debug_callback_failure_is_silent(self, executor, session):
        """on_debug 실행 중 오류가 발생해도 실행은 계속됨"""
        pctx = _make_pctx()
        pctx.client.chat_postMessage.side_effect = Exception("Slack API error")

        captured_on_debug = None

        async def mock_execute(**kwargs):
            nonlocal captured_on_debug
            captured_on_debug = kwargs.get("on_debug")
            if captured_on_debug:
                await captured_on_debug("debug info")
            return ClaudeResult(success=True, output="still works", session_id="s-1")

        mock_adapter = MagicMock()
        mock_adapter.execute = mock_execute
        executor._service_adapter = mock_adapter

        # 예외 없이 정상 완료되어야 함
        executor._execute_remote(
            "1234.5678", "hello",
            on_progress=_noop_progress,
            on_compact=_noop_compact,
            presentation=pctx,
            session_id=None,
            user_message=None,
            on_result=None,
        )


# === 5. 컴팩션 테스트 ===

class TestIntegrationCompaction:
    """compact 이벤트 SSE 전파 → 봇 정상 처리"""

    @pytest.fixture
    def executor(self, tmp_path):
        return _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_compact_callback_forwarded(self, executor, session):
        """on_compact 콜백이 adapter.execute에 전달되는지 확인"""
        pctx = _make_pctx()
        captured_kwargs = {}

        async def mock_execute(**kwargs):
            captured_kwargs.update(kwargs)
            # compact 콜백 호출 시뮬레이션
            if kwargs.get("on_compact"):
                await kwargs["on_compact"]("auto", "컨텍스트 정리됨")
            return ClaudeResult(success=True, output="done", session_id="sess-c")

        mock_adapter = MagicMock()
        mock_adapter.execute = mock_execute

        compact_events = []

        async def on_compact(trigger, message):
            compact_events.append((trigger, message))

        with patch.object(executor, "_get_service_adapter", return_value=mock_adapter):
            executor._execute_remote(
                "1234.5678", "hello",
                on_progress=_noop_progress,
                on_compact=on_compact,
                presentation=pctx,
                session_id=None,
                user_message=None,
                on_result=None,
            )

        assert len(compact_events) == 1
        assert compact_events[0] == ("auto", "컨텍스트 정리됨")


# === supervisor config 환경변수 테스트 ===

class TestSupervisorConfig:
    """supervisor config에서 ProcessConfig.env 필드가 제거되었음을 확인."""

    def test_process_config_has_no_env_field(self):
        """ProcessConfig에 env 필드가 존재하지 않아야 함."""
        from supervisor.config import build_process_configs
        configs = build_process_configs()

        bot_config = next(c for c in configs if c.name == "bot")
        assert not hasattr(bot_config, "env")
