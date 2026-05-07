"""caller_info 조립 헬퍼 테스트 (Phase 4 + 통합 스키마 v1)"""

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
        """전체 스키마 모양이 soul-server Task.caller_info v1과 호환된다.

        v1 스키마 (분석 캐시 §2):
        - top-level: source, user_id, slack, bot_name, [display_name, avatar_url, email]
        - slack sub-dict: channel_id, user_id, [thread_ts]
        - 신원 필드(display_name 등)는 인자가 비면 생략(graceful)
        """
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
        )
        # 신원 필드 미제공 시: top-level은 필수 4개만
        assert set(info.keys()) == {"source", "user_id", "slack", "bot_name"}
        assert set(info["slack"].keys()) == {"channel_id", "user_id", "thread_ts"}

    # === 통합 스키마 v1 신규 케이스 ===

    def test_top_level_user_id_mirrors_slack_user_id(self):
        """top-level user_id는 slack.user_id와 동일값(의도적 중복).

        Push notifier 화이트리스트와 표시 코드가 양쪽 어디서 읽어도 같은 값.
        한쪽만 채우면 안 된다.
        """
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
        )
        assert info["user_id"] == "U0A9ELR53R8"
        assert info["slack"]["user_id"] == "U0A9ELR53R8"
        assert info["user_id"] == info["slack"]["user_id"]

    def test_display_name_avatar_url_present_when_provided(self):
        """display_name·avatar_url·email이 키워드 인자로 주어지면 top-level에 채워진다."""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
            display_name="서소영",
            avatar_url="https://avatars.slack-edge.com/.../image_192.png",
            email="seosoyoung@example.com",
        )
        assert info["display_name"] == "서소영"
        assert info["avatar_url"] == "https://avatars.slack-edge.com/.../image_192.png"
        assert info["email"] == "seosoyoung@example.com"

    def test_display_name_omitted_when_empty_or_none(self):
        """display_name이 빈 문자열·None이면 caller_info에 키 자체가 들어가지 않는다(graceful)."""
        info_none = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            display_name=None,
        )
        info_empty = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            display_name="",
        )
        assert "display_name" not in info_none
        assert "display_name" not in info_empty

    def test_avatar_url_omitted_when_empty_or_none(self):
        """avatar_url이 빈 문자열·None이면 caller_info에 키 자체가 들어가지 않는다(graceful)."""
        info_none = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            avatar_url=None,
        )
        info_empty = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            avatar_url="",
        )
        assert "avatar_url" not in info_none
        assert "avatar_url" not in info_empty

    def test_email_omitted_when_not_provided(self):
        """email이 키워드 인자로 주어지지 않거나 비면 caller_info에 키 자체가 들어가지 않는다."""
        info_default = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
        )
        info_none = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            email=None,
        )
        info_empty = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            email="",
        )
        assert "email" not in info_default
        assert "email" not in info_none
        assert "email" not in info_empty

    def test_partial_identity_only_display_name(self):
        """display_name만 있고 avatar_url 없으면 display_name만 들어간다 (부분 성공)."""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            display_name="서소영",
            avatar_url="",
        )
        assert info["display_name"] == "서소영"
        assert "avatar_url" not in info

    def test_v1_schema_shape_with_full_identity(self):
        """신원 필드 모두 채운 v1 스키마의 전체 키 셋."""
        info = build_slack_caller_info(
            channel_id="C08ABC123",
            user_id="U0A9ELR53R8",
            thread_ts="1234567890.123456",
            display_name="서소영",
            avatar_url="https://avatars.slack-edge.com/.../image_192.png",
            email="seosoyoung@example.com",
        )
        assert set(info.keys()) == {
            "source",
            "user_id",
            "slack",
            "bot_name",
            "display_name",
            "avatar_url",
            "email",
        }
        assert set(info["slack"].keys()) == {"channel_id", "user_id", "thread_ts"}

    def test_backward_compat_existing_callers(self):
        """신원 키워드 인자 없이 위치 인자만 호출하는 기존 호출자 코드 호환.

        ⚪ 비기능 요구사항 #9: 기존 호출자 코드 변경 최소화.
        """
        # 기존 호출 시그니처 — channel_id, user_id, thread_ts만
        info = build_slack_caller_info("C08ABC123", "U0A9ELR53R8", "1234.5678")
        assert info["source"] == "slack"
        assert info["user_id"] == "U0A9ELR53R8"
        assert info["slack"]["channel_id"] == "C08ABC123"
        assert info["slack"]["thread_ts"] == "1234.5678"
        assert info["bot_name"] == BOT_NAME
        # 신원 필드 부재
        assert "display_name" not in info
        assert "avatar_url" not in info
        assert "email" not in info
