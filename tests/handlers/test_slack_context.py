"""build_slack_context() 헬퍼 함수 테스트"""

import pytest

from seosoyoung.slackbot.handlers.message import build_slack_context


class TestBuildSlackContext:
    """build_slack_context() 테스트"""

    def test_channel_message(self):
        """채널 내 메시지: thread_ts == message_ts (상위 스레드 없음)"""
        result = build_slack_context(
            channel="C123ABC",
            user_id="U456DEF",
            thread_ts="1234567890.123456",
        )
        assert "<slack-context>" in result
        assert "</slack-context>" in result
        assert "channel_id: C123ABC" in result
        assert "user_id: U456DEF" in result
        assert "thread_ts: 1234567890.123456" in result
        # 채널 메시지에는 parent_thread_ts가 없어야 함
        assert "parent_thread_ts" not in result

    def test_thread_message(self):
        """스레드 내 메시지: parent_thread_ts가 있음"""
        result = build_slack_context(
            channel="C123ABC",
            user_id="U456DEF",
            thread_ts="1234567890.999999",
            parent_thread_ts="1234567890.123456",
        )
        assert "<slack-context>" in result
        assert "</slack-context>" in result
        assert "channel_id: C123ABC" in result
        assert "user_id: U456DEF" in result
        assert "parent_thread_ts: 1234567890.123456" in result
        assert "thread_ts: 1234567890.999999" in result

    def test_no_thread_ts(self):
        """thread_ts가 None이면 thread_ts 줄 생략"""
        result = build_slack_context(
            channel="C123ABC",
            user_id="U456DEF",
        )
        assert "<slack-context>" in result
        assert "</slack-context>" in result
        assert "channel_id: C123ABC" in result
        assert "user_id: U456DEF" in result
        assert "thread_ts" not in result

    def test_xml_structure_is_well_formed(self):
        """XML 태그가 올바른 순서로 구성되어 있는지 확인"""
        result = build_slack_context(
            channel="C123",
            user_id="U456",
            thread_ts="1.0",
        )
        open_idx = result.index("<slack-context>")
        close_idx = result.index("</slack-context>")
        assert open_idx < close_idx
        # 태그 사이에 메타데이터가 위치
        inner = result[open_idx:close_idx]
        assert "channel_id:" in inner
        assert "user_id:" in inner
