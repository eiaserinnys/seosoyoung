"""handlers/actions.py 단위 테스트

_deliver_input_response_to_soul의 URL 경로 검증.
"""

from unittest.mock import patch, MagicMock

import pytest


class TestDeliverInputResponseToSoul:
    """_deliver_input_response_to_soul URL 경로 검증"""

    def test_url_uses_api_prefix(self):
        """/api/sessions/ 경로를 사용해야 한다 (soulstream-server prefix 준수)."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"success": true}'
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            from seosoyoung.slackbot.handlers.actions import (
                _deliver_input_response_to_soul,
            )

            _deliver_input_response_to_soul(
                agent_session_id="sess-123",
                request_id="req-456",
                question_text="Do you confirm?",
                selected_label="Yes",
            )

        assert "captured" in dir() or captured, "urlopen was not called"
        assert "/api/sessions/" in captured["url"], (
            f"Expected '/api/sessions/' in URL but got: {captured['url']}"
        )
        assert captured["url"].endswith("/api/sessions/sess-123/respond"), (
            f"Expected URL to end with '/api/sessions/sess-123/respond' but got: {captured['url']}"
        )

    def test_url_does_not_use_bare_sessions_prefix(self):
        """URL이 /sessions/ (api prefix 없음)으로 시작하지 않아야 한다."""
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = b'{"success": true}'
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            from seosoyoung.slackbot.handlers.actions import (
                _deliver_input_response_to_soul,
            )

            _deliver_input_response_to_soul(
                agent_session_id="sess-999",
                request_id="req-001",
                question_text="Proceed?",
                selected_label="OK",
            )

        url = captured.get("url", "")
        # soul_url 이후 경로는 반드시 /api/sessions/로 시작해야 함
        # /sessions/sess-999/respond (bare, api prefix 없음) 는 안 됨
        # SEOSOYOUNG_SOUL_URL=http://localhost:4105 (conftest에서 설정)
        import re
        # 호스트 뒤의 경로 부분만 추출
        path_match = re.search(r"https?://[^/]+(/.*)$", url)
        path = path_match.group(1) if path_match else url
        assert path.startswith("/api/"), (
            f"URL path must start with /api/ but got: {path} (full url: {url})"
        )
