"""soulstream/ 모듈 독립성 통합 테스트

soulstream/ 모듈이 외부 의존성(Config, slack_sdk, restart, memory 등) 없이
독립적으로 임포트·인스턴스화·동작할 수 있는지 검증합니다.
"""

import ast
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest


# === 임포트 독립성 테스트 ===

class TestModuleImports:
    """soulstream/ 하위 모듈이 외부 의존성 없이 임포트 가능한지 검증"""

    SUBMODULES = [
        "seosoyoung.slackbot.soulstream",
        "seosoyoung.slackbot.soulstream.types",
        "seosoyoung.slackbot.soulstream.engine_types",
        "seosoyoung.slackbot.soulstream.session",
        "seosoyoung.slackbot.soulstream.session_context",
        "seosoyoung.slackbot.soulstream.intervention",
        "seosoyoung.slackbot.soulstream.message_formatter",
        "seosoyoung.slackbot.soulstream.result_processor",
        "seosoyoung.slackbot.soulstream.executor",
        "seosoyoung.slackbot.soulstream.service_client",
        "seosoyoung.slackbot.soulstream.service_adapter",
    ]

    @pytest.mark.parametrize("module_name", SUBMODULES)
    def test_import_succeeds(self, module_name):
        """각 서브모듈이 ImportError 없이 임포트된다"""
        mod = importlib.import_module(module_name)
        assert mod is not None

    def test_no_config_import(self):
        """soulstream/ 모듈이 seosoyoung.slackbot.config를 직접 import하지 않는다"""
        import seosoyoung.slackbot.soulstream as soulstream_mod
        # reload하여 fresh import 확인
        importlib.reload(soulstream_mod)

        # soulstream 패키지 내부 모듈들의 전역 네임스페이스에 Config가 없어야 함
        from seosoyoung.slackbot.soulstream import types, session, intervention
        for mod in [types, session, intervention]:
            assert "Config" not in dir(mod), f"{mod.__name__}에 Config가 있음"

    def test_intervention_no_slack_types_import(self):
        """intervention.py가 claude/types.py의 Slack 타입을 import하지 않는다"""
        import seosoyoung.slackbot.soulstream.intervention as intervention_mod
        importlib.reload(intervention_mod)

        # CardInfo, SlackClient, SayFunction이 없어야 함
        for name in ["CardInfo", "SlackClient", "SayFunction"]:
            assert name not in dir(intervention_mod), (
                f"intervention.py에 {name}이 있음 — claude/types.py 의존 제거 필요"
            )

    def test_presentation_context_outside_claude(self):
        """PresentationContext가 claude/ 패키지 밖에 위치한다"""
        from seosoyoung.slackbot.presentation.types import PresentationContext
        module_name = PresentationContext.__module__
        assert "claude" not in module_name, (
            f"PresentationContext가 claude/ 안에 있음: {module_name}"
        )
        assert "presentation" in module_name

    def test_executor_no_execution_context(self):
        """executor.py에서 ExecutionContext가 제거되었다"""
        import seosoyoung.slackbot.soulstream.executor as executor_mod
        assert not hasattr(executor_mod, "ExecutionContext"), (
            "executor.py에 ExecutionContext가 여전히 존재함"
        )

    def test_types_no_om_callbacks(self):
        """claude/types.py에서 OM 콜백 타입이 제거되었다"""
        import seosoyoung.slackbot.soulstream.types as types_mod
        for name in ["PrepareMemoryFn", "TriggerObservationFn", "OnCompactOMFlagFn"]:
            assert not hasattr(types_mod, name), (
                f"types.py에 {name}이 여전히 존재함"
            )

    def test_no_external_slackbot_imports(self):
        """soulstream/ 패키지가 slackbot의 다른 모듈을 직접 import하지 않는지 AST 검증"""
        claude_dir = Path(__file__).parent.parent.parent / "src" / "seosoyoung" / "slackbot" / "soulstream"
        assert claude_dir.is_dir(), f"soulstream directory not found: {claude_dir}"
        py_files = list(claude_dir.glob("*.py"))
        assert len(py_files) > 5, f"Too few .py files ({len(py_files)}), path may be wrong"
        violations = []
        for py_file in claude_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # executor.py는 credential_ui, config를 로컬 임포트로 사용 (허용)
                allowed_prefixes = (
                    "seosoyoung.slackbot.soulstream",
                    "seosoyoung.slackbot.formatting",
                    "seosoyoung.slackbot.handlers.credential_ui",
                    "seosoyoung.slackbot.config",
                    "seosoyoung.utils",
                )
                if isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                    if (module.startswith("seosoyoung.slackbot.")
                            and not module.startswith(allowed_prefixes)):
                        violations.append(f"{py_file.name}:{node.lineno} -> {module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        if (module.startswith("seosoyoung.slackbot.")
                                and not module.startswith(allowed_prefixes)):
                            violations.append(f"{py_file.name}:{node.lineno} -> {module}")
        assert violations == [], f"soulstream/ 패키지에서 외부 import 발견: {violations}"


# === Protocol 호환성 테스트 ===

class TestProtocolCompatibility:
    """Protocol 타입이 duck-typing 객체와 호환되는지 검증"""

    def test_card_info_protocol(self):
        """CardInfo Protocol이 duck-typed 객체를 받는다"""
        from seosoyoung.slackbot.soulstream.types import CardInfo

        @dataclass
        class MockCard:
            card_id: str = "test-card-id"
            card_name: str = "테스트 카드"
            card_url: str = "https://trello.com/c/test"
            list_key: str = "in_progress"
            has_execute: bool = True
            session_id: Optional[str] = "sess-123"
            dm_thread_ts: Optional[str] = None

        card = MockCard()
        assert isinstance(card, CardInfo)
        assert card.card_id == "test-card-id"

    def test_slack_client_protocol(self):
        """SlackClient Protocol이 mock 객체와 호환된다"""
        from seosoyoung.slackbot.soulstream.types import SlackClient

        mock_client = MagicMock()
        mock_client.chat_postMessage = MagicMock(return_value={"ts": "123"})
        mock_client.chat_update = MagicMock(return_value={"ok": True})

        assert isinstance(mock_client, SlackClient)


# === 인스턴스화 테스트 ===

class TestInstantiation:
    """핵심 클래스가 외부 의존성 없이 인스턴스화 가능한지 검증"""

    def test_session_creation(self):
        """Session 생성 시 외부 의존성 불필요"""
        from seosoyoung.slackbot.soulstream.session import Session
        session = Session(thread_ts="123.456", channel_id="C123")
        assert session.thread_ts == "123.456"
        assert session.role == "viewer"

    def test_session_manager_creation(self, tmp_path):
        """SessionManager 생성 시 외부 의존성 불필요"""
        from seosoyoung.slackbot.soulstream.session import SessionManager
        mgr = SessionManager(session_dir=tmp_path / "sessions")
        session = mgr.create("ts1", "C1", "U1", "testuser")
        assert session.thread_ts == "ts1"
        retrieved = mgr.get("ts1")
        assert retrieved is not None
        assert retrieved.user_id == "U1"

    def test_session_runtime_creation(self):
        """SessionRuntime 생성 시 외부 의존성 불필요"""
        from seosoyoung.slackbot.soulstream.session import SessionRuntime
        runtime = SessionRuntime()
        lock = runtime.get_session_lock("ts1")
        assert lock is not None
        assert runtime.get_running_session_count() == 0

    def test_intervention_manager_creation(self):
        """InterventionManager 생성 시 외부 의존성 불필요"""
        from seosoyoung.slackbot.soulstream.intervention import InterventionManager
        mgr = InterventionManager()
        assert mgr is not None

    def test_exponential_backoff_creation(self):
        """ExponentialBackoff 생성 시 외부 의존성 불필요"""
        from seosoyoung.slackbot.soulstream.service_client import ExponentialBackoff
        backoff = ExponentialBackoff(base_delay=0.5, max_retries=3)
        assert backoff.should_retry()
        assert backoff.get_delay() == 0.5

    def test_executor_creation_with_stubs(self, tmp_path):
        """ClaudeExecutor가 stub 의존성만으로 인스턴스화된다"""
        from seosoyoung.slackbot.soulstream.session import SessionManager, SessionRuntime
        from seosoyoung.slackbot.soulstream.executor import ClaudeExecutor

        sm = SessionManager(session_dir=tmp_path / "sessions")
        sr = SessionRuntime()
        restart_mgr = MagicMock()

        executor = ClaudeExecutor(
            session_manager=sm,
            session_runtime=sr,
            restart_manager=restart_mgr,
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            update_message_fn=MagicMock(),
        )
        assert executor is not None


# === 엔드투엔드 플로우 테스트 ===

class TestEndToEndFlow:
    """세션 생성 → 실행 컨텍스트 구성 → 결과 처리 플로우가
    외부 의존성 없이 동작하는지 검증"""

    def test_session_lifecycle(self, tmp_path):
        """세션 생성 → 업데이트 → 조회 플로우"""
        from seosoyoung.slackbot.soulstream.session import SessionManager, SessionRuntime

        sm = SessionManager(session_dir=tmp_path / "sessions")
        sr = SessionRuntime()

        # 세션 생성
        session = sm.create("ts1", "C1", "U1", "alice", role="admin")
        assert session.role == "admin"

        # 세션 ID 업데이트
        sm.update_session_id("ts1", "claude-sess-001")
        updated = sm.get("ts1")
        assert updated.session_id == "claude-sess-001"

        # 메시지 카운트 증가
        sm.increment_message_count("ts1")
        assert sm.get("ts1").message_count == 1

        # 실행 상태 추적
        sr.mark_session_running("ts1")
        assert sr.get_running_session_count() == 1

        sr.mark_session_stopped("ts1")
        assert sr.get_running_session_count() == 0

    def test_presentation_context_construction(self, tmp_path):
        """PresentationContext가 stub 객체들로 구성된다"""
        from seosoyoung.slackbot.presentation.types import PresentationContext

        mock_say = MagicMock()
        mock_client = MagicMock()

        pctx = PresentationContext(
            channel="C1",
            thread_ts="ts1",
            msg_ts="msg1",
            say=mock_say,
            client=mock_client,
            effective_role="admin",
        )

        assert pctx.thread_ts == "ts1"
        assert pctx.is_trello_mode is False
        assert pctx.effective_role == "admin"

    def test_message_formatter_independence(self):
        """message_formatter 함수들이 독립적으로 동작한다"""
        from seosoyoung.slackbot.soulstream.message_formatter import (
            format_as_blockquote,
        )

        quoted = format_as_blockquote("test message")
        assert ">" in quoted

