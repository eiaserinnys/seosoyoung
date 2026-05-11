"""plugin_sdk/slack UserInfo dataclass 회귀 테스트 (R-5 atom G-15).

R-5 fix(2026-05-11): UserInfo dataclass에 `avatar_url`(profile.image_192) +
`email`(profile.email) 필드 추가. plugin reaction trigger의 caller_info에
신원 forward (R-2 G-9 fix §9 대칭).
"""

from seosoyoung.plugin_sdk.slack import UserInfo


class TestUserInfoDataclassR5:
    """T-G15-A: UserInfo 신규 필드 default `""` 회귀.

    기존 baseline(R-4 이전)이 깨지지 않도록 *기본 인자만으로 인스턴스화* 가능.
    avatar_url/email 신규 필드가 default `""`라 후행 호출자(SlackBackendImpl)가
    선택적으로 채움.
    """

    def test_minimal_kwargs_default_fields_empty(self):
        """id+name만 → 신규 필드 default `""`, 기존 필드 default 보존."""
        info = UserInfo(id="U12345", name="alice")
        assert info.id == "U12345"
        assert info.name == "alice"
        assert info.real_name == ""
        assert info.display_name == ""
        assert info.is_bot is False
        assert info.avatar_url == ""  # R-5 G-15 신규
        assert info.email == ""        # R-5 G-15 신규

    def test_all_fields_populated(self):
        """모든 필드 박힘 — display_name/avatar_url/email 동시 채움."""
        info = UserInfo(
            id="U12345",
            name="alice",
            real_name="Alice Wonderland",
            display_name="앨리스",
            is_bot=False,
            avatar_url="https://avatars.slack-edge.com/.../alice_192.jpg",
            email="alice@example.com",
        )
        assert info.avatar_url == "https://avatars.slack-edge.com/.../alice_192.jpg"
        assert info.email == "alice@example.com"

    def test_avatar_url_email_independent(self):
        """avatar_url / email 개별 채움 가능 — 한 쪽만 부재 graceful."""
        only_avatar = UserInfo(id="U1", name="bob", avatar_url="https://x.com/b.png")
        assert only_avatar.avatar_url == "https://x.com/b.png"
        assert only_avatar.email == ""

        only_email = UserInfo(id="U2", name="carol", email="c@x.com")
        assert only_email.avatar_url == ""
        assert only_email.email == "c@x.com"
