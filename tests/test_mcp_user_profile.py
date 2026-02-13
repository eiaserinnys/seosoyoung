"""MCP user_profile 도구 단위 테스트"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.mcp.tools.user_profile import (
    VALID_SIZES,
    download_user_avatar,
    get_user_profile,
)


class TestGetUserProfile:
    """get_user_profile 함수 테스트"""

    def test_success(self):
        """정상적인 프로필 조회"""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U08HWT0C6K1",
                "profile": {
                    "display_name": "소영",
                    "real_name": "서소영",
                    "title": "내러티브 봇",
                    "status_text": "작업 중",
                    "status_emoji": ":writing_hand:",
                    "email": "soyoung@example.com",
                    "image_48": "https://avatars.slack.com/48.jpg",
                    "image_192": "https://avatars.slack.com/192.jpg",
                    "image_512": "https://avatars.slack.com/512.png",
                },
            },
        }

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ):
            result = get_user_profile("U08HWT0C6K1")

        assert result["success"] is True
        profile = result["profile"]
        assert profile["user_id"] == "U08HWT0C6K1"
        assert profile["display_name"] == "소영"
        assert profile["real_name"] == "서소영"
        assert profile["title"] == "내러티브 봇"
        assert profile["status_text"] == "작업 중"
        assert profile["email"] == "soyoung@example.com"
        assert "image_48" in profile["image_urls"]
        assert "image_192" in profile["image_urls"]
        assert "image_512" in profile["image_urls"]

    def test_invalid_user_id_empty(self):
        """빈 user_id"""
        result = get_user_profile("")
        assert result["success"] is False
        assert "유효하지 않은" in result["message"]

    def test_invalid_user_id_wrong_prefix(self):
        """잘못된 형식의 user_id"""
        result = get_user_profile("C12345")
        assert result["success"] is False
        assert "유효하지 않은" in result["message"]

    def test_slack_api_error(self):
        """Slack API 호출 실패"""
        mock_client = MagicMock()
        mock_client.users_info.side_effect = Exception("user_not_found")

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ):
            result = get_user_profile("U08HWT0C6K1")

        assert result["success"] is False
        assert "user_not_found" in result["message"]

    def test_empty_profile_fields(self):
        """프로필 필드가 비어 있는 경우"""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {"id": "U08HWT0C6K1", "profile": {}},
        }

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ):
            result = get_user_profile("U08HWT0C6K1")

        assert result["success"] is True
        assert result["profile"]["display_name"] == ""
        assert result["profile"]["image_urls"] == {}


class TestDownloadUserAvatar:
    """download_user_avatar 함수 테스트"""

    @pytest.mark.asyncio
    async def test_success_default_size(self, tmp_path, monkeypatch):
        """기본 크기(512)로 아바타 다운로드 성공"""
        monkeypatch.setattr(
            "seosoyoung.mcp.tools.user_profile.AVATAR_DIR", tmp_path / "avatars"
        )

        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U08HWT0C6K1",
                "profile": {
                    "image_512": "https://avatars.slack.com/user_512.png",
                },
            },
        }

        mock_response = MagicMock()
        mock_response.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ), patch("seosoyoung.mcp.tools.user_profile.httpx.AsyncClient", return_value=mock_http):
            result = await download_user_avatar("U08HWT0C6K1")

        assert result["success"] is True
        assert "file_path" in result
        saved = Path(result["file_path"])
        assert saved.exists()
        assert "U08HWT0C6K1_512" in saved.name

    @pytest.mark.asyncio
    async def test_custom_size(self, tmp_path, monkeypatch):
        """지정 크기로 아바타 다운로드"""
        monkeypatch.setattr(
            "seosoyoung.mcp.tools.user_profile.AVATAR_DIR", tmp_path / "avatars"
        )

        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U08HWT0C6K1",
                "profile": {
                    "image_72": "https://avatars.slack.com/user_72.jpg",
                },
            },
        }

        mock_response = MagicMock()
        mock_response.content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ), patch("seosoyoung.mcp.tools.user_profile.httpx.AsyncClient", return_value=mock_http):
            result = await download_user_avatar("U08HWT0C6K1", size=72)

        assert result["success"] is True
        saved = Path(result["file_path"])
        assert "U08HWT0C6K1_72" in saved.name
        assert saved.suffix == ".jpg"

    @pytest.mark.asyncio
    async def test_invalid_size(self):
        """유효하지 않은 크기"""
        result = await download_user_avatar("U08HWT0C6K1", size=100)
        assert result["success"] is False
        assert "유효하지 않은 size" in result["message"]

    @pytest.mark.asyncio
    async def test_image_url_not_available(self):
        """요청한 크기의 이미지 URL이 없는 경우"""
        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U08HWT0C6K1",
                "profile": {
                    "image_48": "https://avatars.slack.com/user_48.jpg",
                },
            },
        }

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ):
            result = await download_user_avatar("U08HWT0C6K1", size=1024)

        assert result["success"] is False
        assert "이미지 URL 없음" in result["message"]

    @pytest.mark.asyncio
    async def test_download_http_error(self, tmp_path, monkeypatch):
        """HTTP 다운로드 실패"""
        monkeypatch.setattr(
            "seosoyoung.mcp.tools.user_profile.AVATAR_DIR", tmp_path / "avatars"
        )

        mock_client = MagicMock()
        mock_client.users_info.return_value = {
            "ok": True,
            "user": {
                "id": "U08HWT0C6K1",
                "profile": {
                    "image_512": "https://avatars.slack.com/user_512.png",
                },
            },
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("Connection refused"))

        with patch(
            "seosoyoung.mcp.tools.user_profile._get_slack_client",
            return_value=mock_client,
        ), patch("seosoyoung.mcp.tools.user_profile.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await download_user_avatar("U08HWT0C6K1")

        assert result["success"] is False
        assert "다운로드 실패" in result["message"]

    @pytest.mark.asyncio
    async def test_profile_fetch_failure_propagated(self):
        """프로필 조회 실패가 전파됨"""
        result = await download_user_avatar("INVALID")
        assert result["success"] is False
        assert "유효하지 않은" in result["message"]


class TestMCPToolRegistration:
    """MCP 도구 등록 확인 테스트"""

    def test_slack_get_user_profile_registered(self):
        """slack_get_user_profile 도구가 MCP 서버에 등록됨"""
        from seosoyoung.mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "slack_get_user_profile" in list(tools.keys())

    def test_slack_download_user_avatar_registered(self):
        """slack_download_user_avatar 도구가 MCP 서버에 등록됨"""
        from seosoyoung.mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "slack_download_user_avatar" in list(tools.keys())

    def test_get_user_profile_params(self):
        """slack_get_user_profile의 파라미터 스키마 확인"""
        from seosoyoung.mcp.server import mcp

        tool = mcp._tool_manager._tools["slack_get_user_profile"]
        schema = tool.parameters
        assert "user_id" in schema["properties"]

    def test_download_user_avatar_params(self):
        """slack_download_user_avatar의 파라미터 스키마 확인"""
        from seosoyoung.mcp.server import mcp

        tool = mcp._tool_manager._tools["slack_download_user_avatar"]
        schema = tool.parameters
        assert "user_id" in schema["properties"]
        assert "size" in schema["properties"]
