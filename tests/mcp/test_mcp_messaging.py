"""MCP slack_post_message 도구 단위 테스트"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


class TestPostMessageTextOnly:
    """텍스트만 전송하는 post_message 테스트"""

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_send_text_message(self, mock_get_client):
        """텍스트 메시지 전송 성공"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from seosoyoung.mcp.tools.slack_messaging import post_message

        result = post_message(
            channel="C12345",
            text="안녕하세요!",
        )
        assert result["success"] is True
        mock_client.chat_postMessage.assert_called_once_with(
            channel="C12345",
            text="안녕하세요!",
        )

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_send_text_with_thread(self, mock_get_client):
        """스레드에 텍스트 메시지 전송"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from seosoyoung.mcp.tools.slack_messaging import post_message

        result = post_message(
            channel="C12345",
            text="스레드 답글",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is True
        mock_client.chat_postMessage.assert_called_once_with(
            channel="C12345",
            text="스레드 답글",
            thread_ts="1234567890.123456",
        )

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_slack_api_error(self, mock_get_client):
        """Slack API 에러 처리"""
        mock_client = MagicMock()
        mock_client.chat_postMessage.side_effect = Exception("channel_not_found")
        mock_get_client.return_value = mock_client

        from seosoyoung.mcp.tools.slack_messaging import post_message

        result = post_message(
            channel="C_INVALID",
            text="테스트",
        )
        assert result["success"] is False
        assert "channel_not_found" in result["message"]


class TestPostMessageWithFiles:
    """파일 첨부 포함 post_message 테스트"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[3])

    def _make_temp_file(self, suffix=".txt", content=b"test"):
        """workspace 내부에 임시 파일 생성"""
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_text_with_single_file(self, mock_get_client):
        """텍스트 + 파일 1개 전송"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_temp_file()
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="파일 첨부합니다",
                file_paths=tmp_path,
            )
            assert result["success"] is True
            # chat_postMessage 호출 확인
            mock_client.chat_postMessage.assert_called_once()
            # files_upload_v2 호출 확인
            mock_client.files_upload_v2.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_text_with_multiple_files(self, mock_get_client):
        """텍스트 + 파일 여러 개 전송"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp1 = self._make_temp_file(suffix=".txt", content=b"file1")
        tmp2 = self._make_temp_file(suffix=".json", content=b'{"a":1}')
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="파일 2개",
                file_paths=f"{tmp1},{tmp2}",
            )
            assert result["success"] is True
            mock_client.chat_postMessage.assert_called_once()
            assert mock_client.files_upload_v2.call_count == 2
        finally:
            os.unlink(tmp1)
            os.unlink(tmp2)

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_text_with_thread_and_file(self, mock_get_client):
        """스레드에 텍스트 + 파일 전송"""
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ts": "9999.0001"}
        mock_get_client.return_value = mock_client

        tmp_path = self._make_temp_file()
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="스레드에 파일",
                thread_ts="1234567890.123456",
                file_paths=tmp_path,
            )
            assert result["success"] is True
            # 스레드 ts가 전달됨
            call_kwargs = mock_client.chat_postMessage.call_args
            assert call_kwargs.kwargs.get("thread_ts") == "1234567890.123456"
        finally:
            os.unlink(tmp_path)

    def test_file_not_found(self):
        """존재하지 않는 파일 경로"""
        from seosoyoung.mcp.tools.slack_messaging import post_message

        result = post_message(
            channel="C12345",
            text="파일 첨부",
            file_paths="/nonexistent/file.txt",
        )
        assert result["success"] is False
        assert "존재하지 않" in result["message"]

    def test_disallowed_extension(self):
        """허용되지 않는 확장자"""
        tmp_path = self._make_temp_file(suffix=".exe")
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="exe 첨부",
                file_paths=tmp_path,
            )
            assert result["success"] is False
            assert "확장자" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_outside_workspace(self):
        """workspace 외부 파일 거부"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"outside")
            tmp_path = tmp.name

        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="외부 파일",
                file_paths=tmp_path,
            )
            assert result["success"] is False
            assert "workspace" in result["message"].lower() or "허용" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_too_large(self):
        """20MB 초과 파일 거부"""
        tmp_path = self._make_temp_file(content=b"x" * (20 * 1024 * 1024 + 1))
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="큰 파일",
                file_paths=tmp_path,
            )
            assert result["success"] is False
            assert "크기" in result["message"] or "20MB" in result["message"]
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.slack_messaging._get_slack_client")
    def test_file_upload_error_reported(self, mock_get_client):
        """파일 업로드 실패 시 에러 보고"""
        mock_client = MagicMock()
        mock_client.files_upload_v2.side_effect = Exception("upload_failed")
        mock_get_client.return_value = mock_client

        tmp_path = self._make_temp_file()
        try:
            from seosoyoung.mcp.tools.slack_messaging import post_message

            result = post_message(
                channel="C12345",
                text="파일 첨부 실패 테스트",
                file_paths=tmp_path,
            )
            # 텍스트 전송은 성공했지만 파일 업로드 실패 정보가 포함됨
            assert "upload_failed" in result.get("message", "") or result.get("file_errors")
        finally:
            os.unlink(tmp_path)
