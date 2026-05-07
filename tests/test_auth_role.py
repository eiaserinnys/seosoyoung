"""slackbot/auth.py: get_user_role / check_permission 단위 테스트.

caller_info 통합 스키마 v1을 위해 get_user_role이 profile.display_name·image_192·email·is_bot도
반환하도록 확장됐는지 검증한다 (분석 캐시 §2, 정본 하나 원칙).
"""

from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.slackbot.auth import check_permission, get_user_role


# === Config 모킹 ===

@pytest.fixture(autouse=True)
def patch_config():
    """Config.auth.{allowed_users, admin_users, role_tools} 모킹."""
    with patch("seosoyoung.slackbot.auth.Config") as mock_cfg:
        mock_cfg.auth.allowed_users = {"alice", "bob"}
        mock_cfg.auth.admin_users = {"alice"}
        mock_cfg.auth.role_tools = {
            "admin": ["tool_a"],
            "viewer": ["tool_b"],
        }
        yield mock_cfg


def _make_users_info_response(
    *,
    name: str = "alice",
    display_name: str = "서소영",
    real_name: str = "Seo Soyoung",
    image_192: str = "https://avatars.slack-edge.com/ALICE/image_192.png",
    email: str = "alice@example.com",
    is_bot: bool = False,
) -> dict:
    """Slack users.info 응답 페이로드를 합성한다 (실제 API 응답 구조)."""
    return {
        "user": {
            "id": "U_ALICE",
            "name": name,
            "is_bot": is_bot,
            "profile": {
                "display_name": display_name,
                "real_name": real_name,
                "image_72": image_192.replace("_192", "_72"),
                "image_192": image_192,
                "image_512": image_192.replace("_192", "_512"),
                "email": email,
            },
        },
    }


class TestGetUserRoleIdentityFields:
    """get_user_role이 caller_info v1을 위한 신원 필드를 반환한다."""

    def test_returns_display_name_from_profile(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(
            display_name="서소영", real_name="Seo Soyoung",
        )
        info = get_user_role("U_ALICE", client)
        assert info is not None
        assert info["display_name"] == "서소영"

    def test_falls_back_to_real_name_when_display_name_empty(self):
        """profile.display_name이 비면 real_name으로 폴백."""
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(
            display_name="", real_name="Seo Soyoung",
        )
        info = get_user_role("U_ALICE", client)
        assert info["display_name"] == "Seo Soyoung"

    def test_display_name_empty_when_both_missing(self):
        """display_name과 real_name 둘 다 없으면 빈 문자열."""
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(
            display_name="", real_name="",
        )
        info = get_user_role("U_ALICE", client)
        assert info["display_name"] == ""

    def test_returns_avatar_url_from_image_192(self):
        client = MagicMock()
        url = "https://avatars.slack-edge.com/ALICE/image_192.png"
        client.users_info.return_value = _make_users_info_response(image_192=url)
        info = get_user_role("U_ALICE", client)
        assert info["avatar_url"] == url

    def test_avatar_url_empty_when_image_192_missing(self):
        """profile.image_192가 없으면 avatar_url은 빈 문자열 (caller_info에서 누락 처리됨)."""
        client = MagicMock()
        response = _make_users_info_response()
        del response["user"]["profile"]["image_192"]
        client.users_info.return_value = response
        info = get_user_role("U_ALICE", client)
        assert info["avatar_url"] == ""

    def test_returns_email_from_profile(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(email="alice@x.com")
        info = get_user_role("U_ALICE", client)
        assert info["email"] == "alice@x.com"

    def test_email_empty_when_profile_lacks_email(self):
        """profile.email 권한이 없거나 빈 경우 — caller_info에서 누락 처리."""
        client = MagicMock()
        response = _make_users_info_response()
        del response["user"]["profile"]["email"]
        client.users_info.return_value = response
        info = get_user_role("U_ALICE", client)
        assert info["email"] == ""

    def test_returns_is_bot_flag(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(is_bot=True)
        info = get_user_role("U_ALICE", client)
        assert info["is_bot"] is True

    def test_is_bot_defaults_to_false(self):
        client = MagicMock()
        response = _make_users_info_response()
        del response["user"]["is_bot"]
        client.users_info.return_value = response
        info = get_user_role("U_ALICE", client)
        assert info["is_bot"] is False


class TestGetUserRoleBackwardCompat:
    """기존 키(user_id, username, role, allowed_tools) 호환 유지."""

    def test_returns_existing_keys(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(name="alice")
        info = get_user_role("U_ALICE", client)
        assert info["user_id"] == "U_ALICE"
        assert info["username"] == "alice"
        assert info["role"] == "admin"
        assert info["allowed_tools"] == ["tool_a"]

    def test_viewer_role_for_non_admin(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(name="bob")
        info = get_user_role("U_BOB", client)
        assert info["role"] == "viewer"
        assert info["allowed_tools"] == ["tool_b"]


class TestGetUserRoleFailure:
    """Slack API 실패 시 graceful — None 반환 (기존 동작 유지)."""

    def test_returns_none_on_slack_api_error(self):
        from slack_sdk.errors import SlackApiError
        client = MagicMock()
        client.users_info.side_effect = SlackApiError(
            "rate limited", response={"error": "ratelimited"}
        )
        info = get_user_role("U_ALICE", client)
        assert info is None

    def test_returns_none_on_generic_exception(self):
        client = MagicMock()
        client.users_info.side_effect = RuntimeError("network down")
        info = get_user_role("U_ALICE", client)
        assert info is None

    def test_returns_none_on_malformed_response(self):
        """user 키 자체가 없는 응답 — graceful None."""
        client = MagicMock()
        client.users_info.return_value = {}
        info = get_user_role("U_ALICE", client)
        # user 없으면 KeyError → except → None
        assert info is None


class TestCheckPermissionUnchanged:
    """check_permission은 본 카드 범위 외 — 기존 동작 유지 검증."""

    def test_allowed_user(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(name="alice")
        assert check_permission("U_ALICE", client) is True

    def test_disallowed_user(self):
        client = MagicMock()
        client.users_info.return_value = _make_users_info_response(name="charlie")
        assert check_permission("U_CHARLIE", client) is False

    def test_returns_false_on_exception(self):
        client = MagicMock()
        client.users_info.side_effect = RuntimeError("boom")
        assert check_permission("U_ALICE", client) is False
