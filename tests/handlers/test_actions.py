"""AskUserQuestion 응답을 오케스트레이터에 전달한다."""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from seosoyoung.slackbot.handlers.actions import _deliver_input_response, register_action_handlers


def test_deliver_response_to_orchestrator():
    orchestrator = SimpleNamespace(url="https://orch.example", token="orch-token")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{}'
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        assert _deliver_input_response(orchestrator, "sess-123", "req-456", "질문", "예") is True

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://orch.example/api/sessions/sess-123/respond"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer orch-token"
    assert json.loads(request.data) == {"request_id": "req-456", "answers": {"질문": "예"}}


@pytest.mark.parametrize("url,token", [("", "token"), ("https://orch.example", "")])
def test_missing_config_does_not_request(url, token, caplog):
    with patch("urllib.request.urlopen") as urlopen:
        assert _deliver_input_response(SimpleNamespace(url=url, token=token), "s", "r", "q", "a") is False
    urlopen.assert_not_called()
    assert caplog.records


def test_http_error_logs_status_and_body(caplog):
    error = HTTPError("https://orch.example", 404, "Not Found", {}, io.BytesIO(b'{"code":"SESSION_NOT_FOUND"}'))
    with patch("urllib.request.urlopen", side_effect=error):
        assert _deliver_input_response(SimpleNamespace(url="https://orch.example", token="t"), "s", "r", "q", "a") is False
    assert "404" in caplog.text
    assert "SESSION_NOT_FOUND" in caplog.text


def test_button_uses_injected_orchestrator():
    handlers = {}
    app = MagicMock()
    app.action.side_effect = lambda key: lambda fn: handlers.setdefault(key, fn)
    orchestrator = SimpleNamespace(url="https://orch.example", token="token")
    register_action_handlers(app, {
        "orchestrator": orchestrator,
        "restart_manager": MagicMock(),
        "get_running_session_count": MagicMock(),
        "trello_watcher_ref": MagicMock(),
    })
    handler = next(fn for key, fn in handlers.items() if hasattr(key, "pattern") and key.pattern == "input_request_.+")
    body = {"actions": [{"value": json.dumps({"rid": "r", "sid": "s", "q": "q", "a": "a"})}],
            "channel": {"id": "C"}, "message": {"ts": "1"}}
    with patch("seosoyoung.slackbot.handlers.actions._deliver_input_response") as deliver:
        handler(MagicMock(), body, MagicMock())
    deliver.assert_called_once_with(orchestrator, agent_session_id="s", request_id="r", question_text="q", selected_label="a")
