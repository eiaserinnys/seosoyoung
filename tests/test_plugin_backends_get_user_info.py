"""SlackBackendImpl.get_user_info 회귀 테스트 (R-5 atom G-15).

R-5 fix(2026-05-11): `image_192`(avatar_url) + `email` 채움 추가 — plugin
reaction trigger 등이 6-arg `build_slack_caller_info`에 forward.
host slackbot `auth.py:62-63 get_user_role` 패턴과 §9 대칭.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from seosoyoung.slackbot.plugin_backends import SlackBackendImpl


def _make_backend(client_mock: MagicMock | None = None) -> SlackBackendImpl:
    return SlackBackendImpl(client_mock or MagicMock())


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestSlackBackendGetUserInfoR5:
    """T-G15-B/C/D: SlackBackendImpl.get_user_info 신규 필드 채움 회귀."""

    def test_image_192_populated(self):
        """T-G15-B: profile.image_192 → UserInfo.avatar_url."""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "user": {
                "id": "U12345",
                "name": "alice",
                "is_bot": False,
                "profile": {
                    "real_name": "Alice Wonderland",
                    "display_name": "앨리스",
                    "image_192": "https://avatars.slack-edge.com/alice_192.jpg",
                    "email": "alice@example.com",
                },
            },
        }
        backend = _make_backend(mock_client)
        info = _run(backend.get_user_info("U12345"))
        assert info is not None
        assert info.avatar_url == "https://avatars.slack-edge.com/alice_192.jpg"

    def test_email_populated(self):
        """T-G15-C: profile.email → UserInfo.email."""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "user": {
                "id": "U12345",
                "name": "alice",
                "profile": {
                    "email": "alice@example.com",
                },
            },
        }
        backend = _make_backend(mock_client)
        info = _run(backend.get_user_info("U12345"))
        assert info is not None
        assert info.email == "alice@example.com"

    def test_profile_missing_fields_default_empty(self):
        """T-G15-D: profile에 image_192/email 없으면 `""` 폴백 (graceful)."""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "user": {
                "id": "U12345",
                "name": "alice",
                "profile": {},
            },
        }
        backend = _make_backend(mock_client)
        info = _run(backend.get_user_info("U12345"))
        assert info is not None
        assert info.avatar_url == ""
        assert info.email == ""

    def test_existing_fields_still_populated(self):
        """기존 필드(real_name/display_name/is_bot) baseline 회귀 보존."""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "user": {
                "id": "U12345",
                "name": "alice",
                "is_bot": False,
                "profile": {
                    "real_name": "Alice W.",
                    "display_name": "앨리스",
                    "image_192": "https://x.com/a.png",
                    "email": "a@x.com",
                },
            },
        }
        backend = _make_backend(mock_client)
        info = _run(backend.get_user_info("U12345"))
        assert info is not None
        assert info.real_name == "Alice W."
        assert info.display_name == "앨리스"
        assert info.is_bot is False
        # R-5 신규 필드도 채워짐 (회귀로 검증)
        assert info.avatar_url == "https://x.com/a.png"
        assert info.email == "a@x.com"

    def test_api_exception_returns_none(self):
        """기존 baseline 보존 — Slack API 예외 시 None (호출 차단)."""
        mock_client = MagicMock()
        mock_client.users_info.side_effect = RuntimeError("Slack API down")
        backend = _make_backend(mock_client)
        info = _run(backend.get_user_info("U12345"))
        assert info is None
