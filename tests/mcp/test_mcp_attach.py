"""MCP attach 도구 단위 테스트"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGetSlackContext:
    """get_slack_context 도구 테스트"""

    def test_returns_channel_and_thread_ts(self):
        """환경변수에서 채널과 스레드 정보를 반환"""
        with patch.dict(os.environ, {
            "SLACK_CHANNEL": "C12345",
            "SLACK_THREAD_TS": "1234567890.123456",
        }):
            from seosoyoung.mcp.tools.attach import get_slack_context

            result = get_slack_context()
            assert result["channel"] == "C12345"
            assert result["thread_ts"] == "1234567890.123456"

    def test_returns_empty_when_not_set(self):
        """환경변수가 없을 때 빈 문자열 반환"""
        with patch.dict(os.environ, {}, clear=True):
            # 환경변수 제거
            env = os.environ.copy()
            env.pop("SLACK_CHANNEL", None)
            env.pop("SLACK_THREAD_TS", None)
            with patch.dict(os.environ, env, clear=True):
                from seosoyoung.mcp.tools.attach import get_slack_context

                result = get_slack_context()
                assert result["channel"] == ""
                assert result["thread_ts"] == ""


class TestAttachFile:
    """attach_file 도구 테스트"""

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

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_upload_success(self, mock_get_client):
        """정상적인 파일 업로드 성공"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_temp_file()
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is True
            mock_client.files_upload_v2.assert_called_once()
        finally:
            os.unlink(tmp_path)

    def test_file_not_found(self):
        """존재하지 않는 파일"""
        from seosoyoung.mcp.tools.attach import attach_file

        result = attach_file(
            file_path="/nonexistent/file.txt",
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is False
        assert "존재하지 않" in result["message"]

    def test_disallowed_extension(self):
        """허용되지 않는 확장자"""
        tmp_path = self._make_temp_file(suffix=".exe")
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "확장자" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_outside_workspace(self):
        """workspace 외부 파일은 거부"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"test")
            tmp_path = tmp.name

        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "workspace" in result["message"].lower() or "허용" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_too_large(self):
        """20MB 초과 파일 거부"""
        tmp_path = self._make_temp_file(content=b"x" * (20 * 1024 * 1024 + 1))
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "크기" in result["message"] or "20MB" in result["message"]
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_slack_api_error(self, mock_get_client):
        """Slack API 에러 처리"""
        mock_client = MagicMock()
        mock_client.files_upload_v2.side_effect = Exception("Slack API error")
        mock_get_client.return_value = mock_client

        tmp_path = self._make_temp_file()
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "Slack API error" in result["message"]
        finally:
            os.unlink(tmp_path)
