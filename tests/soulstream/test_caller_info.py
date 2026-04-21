"""caller_info 조립 헬퍼 테스트 (Phase 4)"""

from seosoyoung.slackbot.soulstream.caller_info import (
    BOT_NAME,
    build_slack_caller_info,
)


class TestBuildSlackCallerInfo:
    """build_slack_caller_info 단위 테스트"""

    def test_includes_source_slack_and_bot_name(self):
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
        )
        assert info["source"] == "slack"
        assert info["bot_name"] == BOT_NAME == "seosoyoung"

    def test_slack_block_contains_channel_user_thread(self):
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
        )
        slack = info["slack"]
        assert slack["channel_id"] == "C08ABC123"
        assert slack["user_id"] == "U0A9ELR53R8"
        assert slack["thread_ts"] == "1234567890.123456"

    def test_thread_ts_none_omits_field(self):
        """thread_ts가 None이면 slack 블록에서 생략된다."""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts=None,
        )
        assert "thread_ts" not in info["slack"]
        assert info["slack"]["channel_id"] == "C08ABC123"
        assert info["slack"]["user_id"] == "U0A9ELR53R8"

    def test_empty_thread_ts_omits_field(self):
        """빈 문자열 thread_ts도 생략 (falsy 체크)"""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="",
        )
        assert "thread_ts" not in info["slack"]

    def test_schema_shape_matches_soul_server_contract(self):
        """전체 스키마 모양이 soul-server Task.caller_info와 호환된다."""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
        )
        assert set(info.keys()) == {"source", "slack", "bot_name"}
        assert set(info["slack"].keys()) == {"channel_id", "user_id", "thread_ts"}
