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
        assert "[사용자의 요청 컨텍스트는 다음과 같습니다]" in result
        assert "- 채널: C123ABC" in result
        assert "- 사용자: U456DEF" in result
        assert "- 스레드: 1234567890.123456" in result
        # 채널 메시지에는 "상위 스레드"가 없어야 함
        assert "상위 스레드" not in result

    def test_thread_message(self):
        """스레드 내 메시지: parent_thread_ts가 있음"""
        result = build_slack_context(
            channel="C123ABC",
            user_id="U456DEF",
            thread_ts="1234567890.999999",
            parent_thread_ts="1234567890.123456",
        )
        assert "[사용자의 요청 컨텍스트는 다음과 같습니다]" in result
        assert "- 채널: C123ABC" in result
        assert "- 사용자: U456DEF" in result
        assert "- 상위 스레드: 1234567890.123456" in result
        assert "- 스레드: 1234567890.999999" in result

    def test_no_thread_ts(self):
        """thread_ts가 None이면 스레드 줄 생략"""
        result = build_slack_context(
            channel="C123ABC",
            user_id="U456DEF",
        )
        assert "- 채널: C123ABC" in result
        assert "- 사용자: U456DEF" in result
        assert "스레드" not in result
