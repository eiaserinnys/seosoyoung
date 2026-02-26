"""Phase 4 통합 테스트 — remote 모드 전체 흐름 검증

executor → soul (mock) → SSE → 결과 처리까지의 end-to-end 시나리오를 검증합니다.

테스트 시나리오:
1. 기본 흐름: 멘션 → soul 위임 → SSE 스트리밍 → 응답
2. 인터벤션: 실행 중 스레드 답글 → session_id 기반 interrupt + 재실행
3. 역할별 도구: admin vs viewer 도구 제한
4. 디버그 이벤트: rate_limit 경고 → 슬랙 디버그 채널 전달
5. 컴팩션: compact 이벤트 → SSE 전파 + 봇 정상 처리
6. 폴백: soul 다운 시 local 모드 자동 전환
7. 폴백 복귀: soul 복구 시 remote 모드 자동 복귀
8. 헬스 트래커: 쿨다운, 연속 실패 추적
"""

import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from seosoyoung.slackbot.claude.executor import (
    ClaudeExecutor,
    SoulHealthTracker,
    _HEALTH_CHECK_COOLDOWN,
)
from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
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
            # health tracker를 mock하여 항상 healthy
            executor._health_tracker = MagicMock()
            executor._health_tracker.check_health.return_value = True

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


# === 6. 폴백 테스트 ===

class TestIntegrationFallback:
    """soul 프로세스 중단 시 local 모드 자동 전환"""

    @pytest.fixture
    def executor(self, tmp_path):
        ex = _make_executor(
            tmp_path,
            execution_mode="remote",
            soul_url="http://localhost:3105",
            soul_token="test-token",
            soul_client_id="test_bot",
        )
        return ex

    @pytest.fixture
    def session(self, executor):
        return executor.session_manager.create(
            thread_ts="1234.5678",
            channel_id="C123",
            user_id="U123",
            role="admin",
        )

    def test_unhealthy_soul_falls_back_to_local(self, executor, session):
        """soul 다운 → _should_use_remote() = False → local 모드로 실행"""
        # health_tracker를 mock하여 unhealthy 반환
        executor._health_tracker = MagicMock()
        executor._health_tracker.check_health.return_value = False

        pctx = _make_pctx()

        with patch("seosoyoung.slackbot.claude.executor.ClaudeRunner") as MockRunner:
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.output = "local 실행됨"
            mock_result.session_id = "sess-local"
            mock_result.interrupted = False
            mock_result.update_requested = False
            mock_result.restart_requested = False
            mock_result.list_run = None
            mock_result.error = None
            mock_result.usage = None
            mock_runner.run_sync.return_value = mock_result
            MockRunner.return_value = mock_runner

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

            # local runner가 사용되었는지 확인
            MockRunner.assert_called_once()
            # remote adapter는 호출되지 않음

    def test_should_use_remote_returns_false_when_unhealthy(self, executor):
        """_should_use_remote: soul unhealthy → False"""
        executor._health_tracker = MagicMock()
        executor._health_tracker.check_health.return_value = False

        assert executor._should_use_remote() is False

    def test_should_use_remote_returns_true_when_healthy(self, executor):
        """_should_use_remote: soul healthy → True"""
        executor._health_tracker = MagicMock()
        executor._health_tracker.check_health.return_value = True

        assert executor._should_use_remote() is True

    def test_should_use_remote_false_for_local_mode(self, executor):
        """_should_use_remote: execution_mode=local → False"""
        executor.execution_mode = "local"
        assert executor._should_use_remote() is False

    def test_remote_execution_error_marks_unhealthy(self, executor, session):
        """remote 실행 중 연결 오류 → health tracker에 unhealthy 마킹"""
        pctx = _make_pctx()
        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._health_tracker = MagicMock()

        with patch(
            "seosoyoung.slackbot.claude.executor.run_in_new_loop",
            side_effect=ConnectionError("Connection refused"),
        ):
            executor._execute_remote(
                "1234.5678", "hello",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                user_message=None,
                on_result=None,
            )

        # 연결 오류 → mark_unhealthy 호출
        executor._health_tracker.mark_unhealthy.assert_called_once()

    def test_successful_remote_marks_healthy(self, executor, session):
        """성공적 remote 실행 → health tracker에 healthy 마킹"""
        pctx = _make_pctx()
        mock_result = ClaudeResult(success=True, output="ok", session_id="s-1")

        mock_adapter = MagicMock()
        executor._service_adapter = mock_adapter
        executor._health_tracker = MagicMock()

        with patch("seosoyoung.slackbot.claude.executor.run_in_new_loop", return_value=mock_result):
            executor._execute_remote(
                "1234.5678", "hello",
                on_progress=_noop_progress,
                on_compact=_noop_compact,
                presentation=pctx,
                session_id=None,
                user_message=None,
                on_result=None,
            )

        executor._health_tracker.mark_healthy.assert_called_once()


# === 7. 폴백 복귀 테스트 ===

class TestIntegrationFallbackRecovery:
    """soul 복구 시 remote 모드 자동 복귀"""

    def test_recovery_after_failure(self):
        """unhealthy → check_health 성공 → is_healthy = True"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)
        tracker._is_healthy = False
        tracker._consecutive_failures = 3

        # _do_health_check를 mock하여 성공 반환
        with patch.object(tracker, "_do_health_check", return_value=True):
            result = tracker.check_health()

        assert result is True
        assert tracker.is_healthy is True
        assert tracker.consecutive_failures == 0

    def test_mark_healthy_resets_state(self):
        """mark_healthy: 상태 리셋"""
        tracker = SoulHealthTracker("http://localhost:3105")
        tracker._is_healthy = False
        tracker._consecutive_failures = 5

        tracker.mark_healthy()

        assert tracker.is_healthy is True
        assert tracker.consecutive_failures == 0

    def test_mark_unhealthy_increments_failures(self):
        """mark_unhealthy: 연속 실패 카운터 증가"""
        tracker = SoulHealthTracker("http://localhost:3105")
        assert tracker.consecutive_failures == 0

        tracker.mark_unhealthy()
        assert tracker.is_healthy is False
        assert tracker.consecutive_failures == 1

        tracker.mark_unhealthy()
        assert tracker.consecutive_failures == 2


# === 8. SoulHealthTracker 상세 테스트 ===

class TestSoulHealthTracker:
    """헬스 트래커: 쿨다운, 연속 실패 추적"""

    def test_initial_state_is_healthy(self):
        """초기 상태: healthy"""
        tracker = SoulHealthTracker("http://localhost:3105")
        assert tracker.is_healthy is True
        assert tracker.consecutive_failures == 0

    def test_cooldown_returns_cached_result(self):
        """쿨다운 기간 내에는 캐시된 결과 반환 (health check 생략)"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=60)

        # 최근에 체크한 것으로 설정
        tracker._last_check_time = time.monotonic()
        tracker._is_healthy = True

        with patch.object(tracker, "_do_health_check") as mock_check:
            result = tracker.check_health()
            # _do_health_check가 호출되지 않아야 함 (쿨다운 내)
            mock_check.assert_not_called()

        assert result is True

    def test_cooldown_expired_triggers_check(self):
        """쿨다운 만료 시 실제 health check 수행"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)

        with patch.object(tracker, "_do_health_check", return_value=True) as mock_check:
            result = tracker.check_health()
            mock_check.assert_called_once()

        assert result is True

    def test_health_check_failure_transitions_to_unhealthy(self):
        """health check 실패 → unhealthy 전환"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)
        assert tracker.is_healthy is True

        with patch.object(tracker, "_do_health_check", return_value=False):
            result = tracker.check_health()

        assert result is False
        assert tracker.is_healthy is False
        assert tracker.consecutive_failures == 1

    def test_consecutive_failures_tracked(self):
        """연속 실패 횟수 추적"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)

        with patch.object(tracker, "_do_health_check", return_value=False):
            tracker.check_health()
            tracker.check_health()
            tracker.check_health()

        assert tracker.consecutive_failures == 3

    def test_recovery_resets_failures(self):
        """복구 시 실패 카운터 리셋"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)

        with patch.object(tracker, "_do_health_check", return_value=False):
            tracker.check_health()
            tracker.check_health()

        assert tracker.consecutive_failures == 2

        with patch.object(tracker, "_do_health_check", return_value=True):
            tracker.check_health()

        assert tracker.consecutive_failures == 0
        assert tracker.is_healthy is True

    def test_do_health_check_success(self):
        """_do_health_check: HTTP 200 → True"""
        tracker = SoulHealthTracker("http://localhost:3105")

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = tracker._do_health_check()

        assert result is True

    def test_do_health_check_connection_error(self):
        """_do_health_check: 연결 실패 → False"""
        tracker = SoulHealthTracker("http://localhost:3105")
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            result = tracker._do_health_check()

        assert result is False

    def test_do_health_check_timeout(self):
        """_do_health_check: 타임아웃 → False"""
        tracker = SoulHealthTracker("http://localhost:3105")

        with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            result = tracker._do_health_check()

        assert result is False

    def test_thread_safety(self):
        """멀티스레드 환경에서 동시 접근 안전"""
        tracker = SoulHealthTracker("http://localhost:3105", cooldown=0)
        errors = []

        def worker():
            try:
                with patch.object(tracker, "_do_health_check", return_value=True):
                    for _ in range(100):
                        tracker.check_health()
                    tracker.mark_healthy()
                    tracker.mark_unhealthy()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# === supervisor config 환경변수 테스트 ===

class TestSupervisorConfig:
    """supervisor config에서 ProcessConfig.env 필드가 제거되었음을 확인."""

    def test_process_config_has_no_env_field(self):
        """ProcessConfig에 env 필드가 존재하지 않아야 함."""
        from supervisor.config import build_process_configs
        configs = build_process_configs()

        bot_config = next(c for c in configs if c.name == "bot")
        assert not hasattr(bot_config, "env")
