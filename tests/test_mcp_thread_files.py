"""MCP slack_download_thread_files 도구 단위 테스트"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.mcp.tools.thread_files import download_thread_files


class TestDownloadThreadFiles:
    """download_thread_files 함수 테스트"""

    @pytest.mark.asyncio
    async def test_success_with_files(self, tmp_path, monkeypatch):
        """스레드에 파일이 있는 경우 정상 다운로드"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        file_content = b"Hello, World!"

        # Slack conversations.replies 모킹
        mock_slack = MagicMock()
        mock_slack.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {
                    "ts": "1234567890.000001",
                    "text": "Here is a file",
                    "files": [
                        {
                            "id": "F001",
                            "name": "report.txt",
                            "mimetype": "text/plain",
                            "filetype": "txt",
                            "size": len(file_content),
                            "url_private": "https://files.slack.com/report.txt",
                        }
                    ],
                },
                {
                    "ts": "1234567890.000002",
                    "text": "No files here",
                },
            ],
        }

        # httpx 다운로드 모킹
        mock_response = MagicMock()
        mock_response.content = file_content
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch("seosoyoung.mcp.tools.thread_files._get_slack_client", return_value=mock_slack), \
             patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_http):
            result = await download_thread_files("C12345", "1234567890.000000")

        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0]["original_name"] == "report.txt"
        assert result["files"][0]["message_ts"] == "1234567890.000001"

    @pytest.mark.asyncio
    async def test_no_files_in_thread(self):
        """파일이 없는 스레드"""
        mock_slack = MagicMock()
        mock_slack.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {"ts": "1234567890.000001", "text": "Hello"},
                {"ts": "1234567890.000002", "text": "World"},
            ],
        }

        with patch("seosoyoung.mcp.tools.thread_files._get_slack_client", return_value=mock_slack):
            result = await download_thread_files("C12345", "1234567890.000000")

        assert result["success"] is True
        assert len(result["files"]) == 0
        assert "파일 없음" in result["message"]

    @pytest.mark.asyncio
    async def test_multiple_files_across_messages(self, tmp_path, monkeypatch):
        """여러 메시지에 걸친 다수의 파일"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        mock_slack = MagicMock()
        mock_slack.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {
                    "ts": "1234567890.000001",
                    "text": "File 1",
                    "files": [
                        {
                            "id": "F001",
                            "name": "doc1.txt",
                            "mimetype": "text/plain",
                            "filetype": "txt",
                            "size": 10,
                            "url_private": "https://files.slack.com/doc1.txt",
                        },
                    ],
                },
                {
                    "ts": "1234567890.000002",
                    "text": "File 2 and 3",
                    "files": [
                        {
                            "id": "F002",
                            "name": "image.png",
                            "mimetype": "image/png",
                            "filetype": "png",
                            "size": 200,
                            "url_private": "https://files.slack.com/image.png",
                        },
                        {
                            "id": "F003",
                            "name": "data.json",
                            "mimetype": "application/json",
                            "filetype": "json",
                            "size": 50,
                            "url_private": "https://files.slack.com/data.json",
                        },
                    ],
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.content = b"content"
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch("seosoyoung.mcp.tools.thread_files._get_slack_client", return_value=mock_slack), \
             patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_http):
            result = await download_thread_files("C12345", "1234567890.000000")

        assert result["success"] is True
        assert len(result["files"]) == 3
        names = [f["original_name"] for f in result["files"]]
        assert "doc1.txt" in names
        assert "image.png" in names
        assert "data.json" in names
        # message_ts 확인
        assert result["files"][0]["message_ts"] == "1234567890.000001"
        assert result["files"][1]["message_ts"] == "1234567890.000002"

    @pytest.mark.asyncio
    async def test_slack_api_error(self):
        """Slack API 호출 실패"""
        mock_slack = MagicMock()
        mock_slack.conversations_replies.side_effect = Exception("channel_not_found")

        with patch("seosoyoung.mcp.tools.thread_files._get_slack_client", return_value=mock_slack):
            result = await download_thread_files("C_INVALID", "1234567890.000000")

        assert result["success"] is False
        assert "channel_not_found" in result["message"]

    @pytest.mark.asyncio
    async def test_partial_download_failure(self, tmp_path, monkeypatch):
        """일부 파일 다운로드 실패 시 성공한 파일만 반환"""
        monkeypatch.setattr("seosoyoung.slack.file_handler.TMP_DIR", tmp_path / "slack_files")

        mock_slack = MagicMock()
        mock_slack.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {
                    "ts": "1234567890.000001",
                    "text": "Files",
                    "files": [
                        {
                            "id": "F001",
                            "name": "good.txt",
                            "mimetype": "text/plain",
                            "filetype": "txt",
                            "size": 10,
                            "url_private": "https://files.slack.com/good.txt",
                        },
                        {
                            "id": "F002",
                            "name": "bad.txt",
                            "mimetype": "text/plain",
                            "filetype": "txt",
                            "size": 10,
                            "url_private": "",  # 빈 URL → 다운로드 실패
                        },
                    ],
                },
            ],
        }

        mock_response = MagicMock()
        mock_response.content = b"good content"
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock()

        with patch("seosoyoung.mcp.tools.thread_files._get_slack_client", return_value=mock_slack), \
             patch("seosoyoung.slack.file_handler.httpx.AsyncClient", return_value=mock_http):
            result = await download_thread_files("C12345", "1234567890.000000")

        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0]["original_name"] == "good.txt"


class TestMCPToolRegistration:
    """MCP 도구 등록 확인 테스트"""

    def test_slack_download_thread_files_registered(self):
        """slack_download_thread_files 도구가 MCP 서버에 등록됨"""
        from seosoyoung.mcp.server import mcp

        tools = mcp._tool_manager._tools
        tool_names = list(tools.keys())
        assert "slack_download_thread_files" in tool_names

    def test_tool_has_correct_params(self):
        """도구가 올바른 파라미터를 가짐"""
        from seosoyoung.mcp.server import mcp

        tool = mcp._tool_manager._tools["slack_download_thread_files"]
        # FastMCP Tool 객체의 파라미터 스키마 확인
        schema = tool.parameters
        assert "channel" in schema["properties"]
        assert "thread_ts" in schema["properties"]


class TestRoleToolsConsistency:
    """ROLE_TOOLS 일관성 테스트"""

    def test_admin_role_includes_thread_files_tool(self):
        """admin 역할에 thread_files 도구가 포함됨"""
        from seosoyoung.config import Config

        tool_name = "mcp__seosoyoung-attach__slack_download_thread_files"
        assert tool_name in Config.auth.role_tools["admin"]

