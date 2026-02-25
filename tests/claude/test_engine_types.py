"""engine_types 모듈 단위 테스트

EngineResult, RoleConfig 데이터 클래스 검증.
"""

from dataclasses import fields
from pathlib import Path
from typing import Optional

import pytest


class TestEngineResult:
    """EngineResult 데이터 클래스 테스트"""

    def test_basic_creation(self):
        """기본 생성"""
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        result = EngineResult(success=True, output="Hello")
        assert result.success is True
        assert result.output == "Hello"
        assert result.session_id is None
        assert result.error is None
        assert result.is_error is False
        assert result.interrupted is False
        assert result.usage is None
        assert result.collected_messages == []

    def test_full_creation(self):
        """모든 필드를 지정하여 생성"""
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        msgs = [{"role": "assistant", "content": "hi"}]
        result = EngineResult(
            success=False,
            output="error output",
            session_id="sess-001",
            error="something went wrong",
            is_error=True,
            interrupted=True,
            usage={"input_tokens": 100, "output_tokens": 50},
            collected_messages=msgs,
        )
        assert result.success is False
        assert result.session_id == "sess-001"
        assert result.error == "something went wrong"
        assert result.is_error is True
        assert result.interrupted is True
        assert result.usage["input_tokens"] == 100
        assert result.collected_messages == msgs

    def test_no_application_markers(self):
        """EngineResult에 응용 마커 필드가 없어야 한다"""
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        field_names = {f.name for f in fields(EngineResult)}
        # 이 필드들은 응용 레이어에 속하므로 EngineResult에 있으면 안 됨
        assert "update_requested" not in field_names
        assert "restart_requested" not in field_names
        assert "list_run" not in field_names
        assert "anchor_ts" not in field_names

    def test_collected_messages_is_independent(self):
        """collected_messages 기본값이 인스턴스 간에 공유되지 않는다"""
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        r1 = EngineResult(success=True, output="a")
        r2 = EngineResult(success=True, output="b")
        r1.collected_messages.append({"role": "user"})
        assert len(r2.collected_messages) == 0


class TestRoleConfig:
    """RoleConfig 데이터 클래스 테스트"""

    def test_default_creation(self):
        """기본값으로 생성"""
        from seosoyoung.slackbot.claude.engine_types import RoleConfig

        config = RoleConfig()
        assert config.allowed_tools is None
        assert config.disallowed_tools is None
        assert config.mcp_config_path is None

    def test_full_creation(self):
        """모든 필드 지정"""
        from seosoyoung.slackbot.claude.engine_types import RoleConfig

        config = RoleConfig(
            allowed_tools=["Read", "Write"],
            disallowed_tools=["WebFetch"],
            mcp_config_path=Path("/tmp/mcp.json"),
        )
        assert config.allowed_tools == ["Read", "Write"]
        assert config.disallowed_tools == ["WebFetch"]
        assert config.mcp_config_path == Path("/tmp/mcp.json")

    def test_no_role_name(self):
        """RoleConfig에 역할 이름 필드가 없어야 한다"""
        from seosoyoung.slackbot.claude.engine_types import RoleConfig

        field_names = {f.name for f in fields(RoleConfig)}
        assert "role" not in field_names
        assert "role_name" not in field_names
        assert "name" not in field_names


class TestCallbackTypes:
    """엔진 전용 콜백 타입 테스트"""

    def test_progress_callback_type_exists(self):
        """ProgressCallback 타입이 engine_types에 존재"""
        from seosoyoung.slackbot.claude.engine_types import ProgressCallback
        assert ProgressCallback is not None

    def test_compact_callback_type_exists(self):
        """CompactCallback 타입이 engine_types에 존재"""
        from seosoyoung.slackbot.claude.engine_types import CompactCallback
        assert CompactCallback is not None

    def test_intervention_callback_type_exists(self):
        """InterventionCallback 타입이 engine_types에 존재"""
        from seosoyoung.slackbot.claude.engine_types import InterventionCallback
        assert InterventionCallback is not None
