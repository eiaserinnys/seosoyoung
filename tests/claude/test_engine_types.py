"""engine_types 모듈 단위 테스트

EngineResult, RoleConfig, EngineEventType, EngineEvent, EventCallback 검증.
"""

from dataclasses import fields
from pathlib import Path
from typing import Optional
import time

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


class TestEngineEventType:
    """EngineEventType enum 테스트"""

    def test_all_members_exist(self):
        """4가지 이벤트 타입이 모두 존재"""
        from seosoyoung.slackbot.claude.engine_types import EngineEventType

        assert EngineEventType.TEXT_DELTA
        assert EngineEventType.TOOL_START
        assert EngineEventType.TOOL_RESULT
        assert EngineEventType.RESULT

    def test_total_count(self):
        """정확히 4개의 이벤트 타입"""
        from seosoyoung.slackbot.claude.engine_types import EngineEventType

        assert len(EngineEventType) == 4

    def test_string_values(self):
        """값이 snake_case 문자열"""
        from seosoyoung.slackbot.claude.engine_types import EngineEventType

        assert EngineEventType.TEXT_DELTA.value == "text_delta"
        assert EngineEventType.TOOL_START.value == "tool_start"
        assert EngineEventType.TOOL_RESULT.value == "tool_result"
        assert EngineEventType.RESULT.value == "result"

    def test_is_enum(self):
        """EngineEventType이 Enum 서브클래스"""
        from enum import Enum
        from seosoyoung.slackbot.claude.engine_types import EngineEventType

        assert issubclass(EngineEventType, Enum)

    def test_lookup_by_value(self):
        """값으로 역조회 가능"""
        from seosoyoung.slackbot.claude.engine_types import EngineEventType

        assert EngineEventType("text_delta") is EngineEventType.TEXT_DELTA
        assert EngineEventType("result") is EngineEventType.RESULT


class TestEngineEvent:
    """EngineEvent dataclass 테스트"""

    def test_basic_creation(self):
        """type만 지정하여 생성 — data/timestamp는 기본값"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        event = EngineEvent(type=EngineEventType.TEXT_DELTA)
        assert event.type is EngineEventType.TEXT_DELTA
        assert event.data == {}
        assert isinstance(event.timestamp, float)

    def test_timestamp_auto_set(self):
        """timestamp가 현재 시각으로 자동 설정"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        before = time.time()
        event = EngineEvent(type=EngineEventType.RESULT)
        after = time.time()

        assert before <= event.timestamp <= after

    def test_data_independence(self):
        """data 기본값이 인스턴스 간 공유되지 않음"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        e1 = EngineEvent(type=EngineEventType.TOOL_START)
        e2 = EngineEvent(type=EngineEventType.TOOL_START)
        e1.data["tool_name"] = "Read"
        assert "tool_name" not in e2.data

    def test_text_delta_payload(self):
        """TEXT_DELTA 이벤트 페이로드 패턴"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        event = EngineEvent(
            type=EngineEventType.TEXT_DELTA,
            data={"text": "분석 중..."},
        )
        assert event.data["text"] == "분석 중..."

    def test_tool_start_payload(self):
        """TOOL_START 이벤트 페이로드 패턴"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        event = EngineEvent(
            type=EngineEventType.TOOL_START,
            data={"tool_name": "Read", "tool_input": {"file_path": "/tmp/a.txt"}},
        )
        assert event.data["tool_name"] == "Read"
        assert event.data["tool_input"]["file_path"] == "/tmp/a.txt"

    def test_result_payload(self):
        """RESULT 이벤트 페이로드 패턴"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        event = EngineEvent(
            type=EngineEventType.RESULT,
            data={"success": True, "output": "완료", "error": None},
        )
        assert event.data["success"] is True
        assert event.data["error"] is None

    def test_custom_timestamp(self):
        """명시적 timestamp 지정 가능"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent, EngineEventType

        ts = 1700000000.0
        event = EngineEvent(type=EngineEventType.RESULT, timestamp=ts)
        assert event.timestamp == ts

    def test_fields(self):
        """dataclass 필드 목록 확인"""
        from seosoyoung.slackbot.claude.engine_types import EngineEvent

        field_names = {f.name for f in fields(EngineEvent)}
        assert field_names == {"type", "data", "timestamp"}


class TestEventCallback:
    """EventCallback 타입 alias 테스트"""

    def test_event_callback_exists(self):
        """EventCallback 타입이 engine_types에 존재"""
        from seosoyoung.slackbot.claude.engine_types import EventCallback
        assert EventCallback is not None

    def test_no_conflict_with_existing_callbacks(self):
        """기존 콜백 타입들과 함께 import 가능"""
        from seosoyoung.slackbot.claude.engine_types import (
            CompactCallback,
            EventCallback,
            InterventionCallback,
            ProgressCallback,
        )
        # 모두 None이 아니어야 하고, 서로 다른 객체여야 함
        callbacks = [ProgressCallback, CompactCallback, InterventionCallback, EventCallback]
        assert all(cb is not None for cb in callbacks)
        # 이름 기준으로 서로 다른지 확인 (typing alias는 동등 비교가 복잡하므로 repr 활용)
        reprs = [repr(cb) for cb in callbacks]
        assert len(set(reprs)) == 4
