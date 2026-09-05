"""Slack bot management bootstrap contract tests."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from cogito import Reflector
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seosoyoung.slackbot import __main__ as bootstrap
from seosoyoung.slackbot import shutdown as shutdown_module
from seosoyoung.slackbot.shutdown import (
    ManagementServerStartupError,
    ShutdownDispatcher,
    start_management_server,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _reflect_app(on_reflect=lambda: None) -> FastAPI:
    app = FastAPI()

    @app.get("/reflect")
    async def reflect():
        on_reflect()
        return {"identity": {"name": "test"}}

    return app


class TestManagementServerStartup:
    @pytest.mark.timeout(10)
    def test_returns_only_after_real_reflect_response(self):
        reflected = threading.Event()
        handle = start_management_server(
            _reflect_app(reflected.set),
            _free_port(),
            startup_timeout=5.0,
        )
        try:
            assert reflected.is_set(), "startup must probe the real /reflect handler"
        finally:
            handle.stop()

    @pytest.mark.timeout(5)
    def test_early_thread_exit_is_failure_not_ready(self, monkeypatch, caplog):
        class EarlyExitServer:
            started = False
            should_exit = False

            def __init__(self, _config):
                pass

            def run(self):
                return None

        monkeypatch.setattr(shutdown_module.uvicorn, "Server", EarlyExitServer)
        caplog.set_level(logging.INFO)

        with pytest.raises(ManagementServerStartupError, match="before readiness"):
            start_management_server(_reflect_app(), 3106, startup_timeout=0.1)

        assert "Management server ready" not in caplog.text

    @pytest.mark.timeout(5)
    def test_thread_exception_is_propagated_to_caller(self, monkeypatch):
        class FailingServer:
            started = False
            should_exit = False

            def __init__(self, _config):
                pass

            def run(self):
                raise OSError("bind failed")

        monkeypatch.setattr(shutdown_module.uvicorn, "Server", FailingServer)

        with pytest.raises(ManagementServerStartupError) as raised:
            start_management_server(_reflect_app(), 3106, startup_timeout=0.1)

        assert isinstance(raised.value.__cause__, OSError)

    @pytest.mark.timeout(5)
    def test_started_server_without_reflect_never_reports_ready(self, caplog):
        caplog.set_level(logging.INFO)

        with pytest.raises(ManagementServerStartupError, match="/reflect"):
            start_management_server(FastAPI(), _free_port(), startup_timeout=0.2)

        assert "Management server ready" not in caplog.text

    @pytest.mark.timeout(5)
    def test_bind_failure_is_propagated(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = int(occupied.getsockname()[1])

            with pytest.raises(ManagementServerStartupError):
                start_management_server(
                    _reflect_app(),
                    port,
                    startup_timeout=1.0,
                )

    @pytest.mark.timeout(5)
    def test_startup_timeout_stops_slow_lifespan_thread_before_returning(self):
        @asynccontextmanager
        async def slow_lifespan(_app):
            await asyncio.sleep(0.6)
            yield

        app = FastAPI(lifespan=slow_lifespan)
        port = _free_port()
        threads_before = {thread.ident for thread in threading.enumerate()}

        with pytest.raises(ManagementServerStartupError, match="/reflect"):
            start_management_server(app, port, startup_timeout=0.05)

        leaked = [
            thread
            for thread in threading.enumerate()
            if thread.name == "slackbot-management"
            and thread.ident not in threads_before
            and thread.is_alive()
        ]
        assert leaked == []
        with socket.socket() as rebound:
            rebound.bind(("127.0.0.1", port))


class TestShutdownDispatcher:
    def test_request_before_import_blocks_runtime(self):
        dispatcher = ShutdownDispatcher()

        dispatcher.request_shutdown()

        assert dispatcher.begin_runtime_import() is False

    def test_request_during_import_is_delivered_once_and_blocks_runtime(self):
        dispatcher = ShutdownDispatcher()
        delivered = []
        assert dispatcher.begin_runtime_import() is True

        dispatcher.request_shutdown()
        dispatcher.request_shutdown()
        dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))
        dispatcher.complete_shutdown_response()

        assert delivered == ["shutdown"]
        runtime = Mock()
        assert dispatcher.run_runtime(runtime) is False
        runtime.assert_not_called()

    def test_request_between_handler_bind_and_runtime_start_blocks_runtime(self):
        dispatcher = ShutdownDispatcher()
        delivered = []
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))

        dispatcher.request_shutdown()
        dispatcher.complete_shutdown_response()

        runtime = Mock()
        assert dispatcher.run_runtime(runtime) is False
        runtime.assert_not_called()
        assert delivered == ["shutdown"]

    def test_request_after_runtime_start_is_delivered_once(self):
        dispatcher = ShutdownDispatcher()
        delivered = []
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))
        runtime = Mock(side_effect=lambda entered: entered())
        assert dispatcher.run_runtime(runtime) is True

        dispatcher.request_shutdown()
        dispatcher.request_shutdown()
        dispatcher.complete_shutdown_response()
        dispatcher.complete_shutdown_response()

        runtime.assert_called_once()
        assert callable(runtime.call_args.args[0])
        assert delivered == ["shutdown"]

    def test_runtime_invocation_and_request_have_one_atomic_order(self):
        dispatcher = ShutdownDispatcher()
        events = []
        request_runtime = threading.Event()
        request_done = threading.Event()
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(lambda: events.append("shutdown-delivered"))

        def request_shutdown():
            request_runtime.wait()
            dispatcher.request_shutdown()
            events.append("shutdown-requested")
            request_done.set()

        requester = threading.Thread(target=request_shutdown)
        requester.start()

        def runtime_main(entered):
            events.append("runtime-main")
            entered()
            request_runtime.set()
            request_done.wait(1.0)

        assert dispatcher.run_runtime(runtime_main) is True
        requester.join(1.0)

        assert events[:2] == ["runtime-main", "shutdown-requested"]

    def test_callback_failure_is_preserved_without_automatic_retry(self):
        dispatcher = ShutdownDispatcher()
        failure = RuntimeError("shutdown failed after an unknown side effect")
        handler = Mock(side_effect=failure)
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(handler)
        dispatcher.request_shutdown()

        with pytest.raises(RuntimeError) as first:
            dispatcher.complete_shutdown_response()
        with pytest.raises(RuntimeError) as second:
            dispatcher.complete_shutdown_response()

        assert first.value is failure
        assert second.value is failure
        handler.assert_called_once_with()


def test_bootstrap_shutdown_before_import_never_calls_runtime_loader(monkeypatch):
    captured = {}
    handle = Mock()

    def create_app(_reflector, dispatcher):
        captured["dispatcher"] = dispatcher
        return object()

    def start_server(_app, _port):
        captured["dispatcher"].request_shutdown()
        return handle

    monkeypatch.setattr(bootstrap, "create_management_app", create_app)
    monkeypatch.setattr(bootstrap, "start_management_server", start_server)
    runtime_loader = Mock()

    with pytest.raises(SystemExit) as raised:
        bootstrap.run(port=3106, runtime_loader=runtime_loader)

    assert raised.value.code == 43
    runtime_loader.assert_not_called()
    handle.stop.assert_called_once_with()


def test_bootstrap_shutdown_during_import_never_starts_runtime(monkeypatch):
    captured = {}
    delivered = []
    runtime_start = Mock()
    handle = Mock()

    def create_app(_reflector, dispatcher):
        captured["dispatcher"] = dispatcher
        return object()

    def load_runtime():
        captured["dispatcher"].request_shutdown()
        captured["dispatcher"].complete_shutdown_response()
        return SimpleNamespace(
            handle_management_shutdown=lambda: delivered.append("shutdown"),
            main=runtime_start,
        )

    monkeypatch.setattr(bootstrap, "create_management_app", create_app)
    monkeypatch.setattr(bootstrap, "start_management_server", lambda _app, _port: handle)

    bootstrap.run(port=3106, runtime_loader=load_runtime)

    assert delivered == ["shutdown"]
    runtime_start.assert_not_called()
    handle.stop.assert_called_once_with()


def test_management_handler_preserves_restart_exit_in_isolated_process():
    script = r"""
import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock

slack_bolt = ModuleType("slack_bolt")
slack_app = MagicMock()
slack_app.event = MagicMock(return_value=lambda function: function)
slack_bolt.App = MagicMock(return_value=slack_app)
socket_mode = ModuleType("slack_bolt.adapter.socket_mode")
socket_mode.SocketModeHandler = MagicMock()
sys.modules["slack_bolt"] = slack_bolt
sys.modules["slack_bolt.adapter.socket_mode"] = socket_mode

from seosoyoung.slackbot import main as runtime
from seosoyoung.slackbot.shutdown import ShutdownDispatcher

runtime.session_runtime.get_running_session_count = MagicMock(return_value=0)
runtime.notify_shutdown = MagicMock()
runtime.os._exit = MagicMock()
runtime.handle_management_shutdown()
runtime.os._exit.assert_called_once_with(runtime.RestartType.RESTART.value)
assert runtime.RestartType.RESTART.value == 43

runtime.init_bot_user_id = MagicMock()
runtime.init_plugin_backends = MagicMock()
runtime._load_plugins = MagicMock()
runtime._dispatch_plugin_startup = MagicMock()
runtime.notify_startup = MagicMock()
handler = runtime.SocketModeHandler.return_value
runtime.main(lambda: None)
runtime._dispatch_plugin_startup.assert_called_once_with()
runtime.notify_startup.assert_called_once_with()
runtime.SocketModeHandler.assert_called_once_with(runtime.app, runtime.Config.slack.app_token)
handler.start.assert_called_once_with()
handler.connect.assert_not_called()

handler.start.reset_mock()
sdk_start_entered = threading.Event()
release_sdk_start = threading.Event()
shutdown_delivered = threading.Event()
handler.start.side_effect = lambda: (sdk_start_entered.set(), release_sdk_start.wait(1.0))
dispatcher = ShutdownDispatcher()
assert dispatcher.begin_runtime_import() is True
dispatcher.bind_shutdown_handler(shutdown_delivered.set)
runtime_thread = threading.Thread(target=lambda: dispatcher.run_runtime(runtime.main))
runtime_thread.start()
assert sdk_start_entered.wait(1.0) is True
assert dispatcher.request_shutdown() is True
dispatcher.complete_shutdown_response()
assert shutdown_delivered.wait(0.1) is True
release_sdk_start.set()
runtime_thread.join(1.0)
assert runtime_thread.is_alive() is False
handler.start.assert_called_once_with()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[2] / "src")

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr[-2000:]


def _call_shutdown_with_failed_final_send(app: FastAPI) -> None:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/shutdown",
        "raw_path": b"/shutdown",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 3106),
        "root_path": "",
    }
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if (
            message["type"] == "http.response.body"
            and not message.get("more_body", False)
        ):
            raise ConnectionError("client disconnected before final body send")

    asyncio.run(app(scope, receive, send))


def test_failed_final_send_still_delivers_accepted_shutdown_once():
    delivered = []
    dispatcher = ShutdownDispatcher()
    assert dispatcher.begin_runtime_import() is True
    dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))
    reflector = Reflector(
        name="bot", description="test", version_from="1.0.0", language="python", port=3106,
    )
    app = shutdown_module.create_management_app(reflector, dispatcher)

    with pytest.raises(ConnectionError, match="client disconnected"):
        _call_shutdown_with_failed_final_send(app)

    assert delivered == ["shutdown"]
    duplicate = TestClient(app).post("/shutdown")
    assert duplicate.status_code == 200
    assert delivered == ["shutdown"]


def test_callback_failure_is_visible_to_later_shutdown_http_without_retry():
    handler = Mock(side_effect=RuntimeError("shutdown callback failed"))
    dispatcher = ShutdownDispatcher()
    assert dispatcher.begin_runtime_import() is True
    dispatcher.bind_shutdown_handler(handler)
    reflector = Reflector(
        name="bot", description="test", version_from="1.0.0", language="python", port=3106,
    )
    client = TestClient(
        shutdown_module.create_management_app(reflector, dispatcher),
        raise_server_exceptions=False,
    )

    first = client.post("/shutdown")
    duplicate = client.post("/shutdown")

    assert first.status_code == 200
    assert duplicate.status_code == 500
    assert duplicate.json() == {
        "status": "shutdown_failed",
        "code": "shutdown_callback_failed",
    }
    handler.assert_called_once_with()


@pytest.mark.timeout(5)
def test_callback_failure_is_visible_through_live_management_http():
    handler = Mock(side_effect=RuntimeError("shutdown callback failed"))
    dispatcher = ShutdownDispatcher()
    assert dispatcher.begin_runtime_import() is True
    dispatcher.bind_shutdown_handler(handler)
    port = _free_port()
    reflector = Reflector(
        name="bot", description="test", version_from="1.0.0", language="python", port=port,
    )
    handle = start_management_server(
        shutdown_module.create_management_app(reflector, dispatcher),
        port,
        startup_timeout=2.0,
    )

    try:
        request = Request(
            f"http://127.0.0.1:{port}/shutdown",
            data=b"",
            method="POST",
        )
        with urlopen(request, timeout=2.0) as response:
            assert response.status == 200
            assert response.read()

        with pytest.raises(HTTPError) as failed:
            urlopen(request, timeout=2.0)
        assert failed.value.code == 500
        assert b'"code":"shutdown_callback_failed"' in failed.value.read()
        handler.assert_called_once_with()
        assert handle.thread.is_alive()
        with urlopen(f"http://127.0.0.1:{port}/reflect", timeout=2.0) as response:
            assert response.status == 200
    finally:
        handle.stop()


@pytest.mark.timeout(5)
def test_runtime_loader_runs_only_after_management_http_is_ready():
    port = _free_port()
    events: list[object] = []

    def load_runtime():
        with urlopen(f"http://127.0.0.1:{port}/reflect", timeout=1.0) as response:
            events.append(("reflect", response.status))
        events.append("runtime-import")
        return SimpleNamespace(
            handle_management_shutdown=lambda: events.append("shutdown"),
            main=lambda entered: (entered(), events.append("runtime-start")),
        )

    bootstrap.run(port=port, runtime_loader=load_runtime)

    assert events == [("reflect", 200), "runtime-import", "runtime-start"]


@pytest.mark.timeout(5)
def test_shutdown_delivery_follows_final_asgi_response_body_send():
    port = _free_port()
    events = []
    dispatcher = ShutdownDispatcher()
    assert dispatcher.begin_runtime_import() is True
    dispatcher.bind_shutdown_handler(lambda: events.append("shutdown-delivered"))
    reflector = Reflector(
        name="bot",
        description="test",
        version_from="1.0.0",
        language="python",
        port=port,
    )
    app = shutdown_module.create_management_app(reflector, dispatcher)

    class DelayedFinalBody:
        def __init__(self, wrapped_app):
            self.wrapped_app = wrapped_app

        async def __call__(self, scope, receive, send):
            async def observed_send(message):
                if (
                    scope["type"] == "http"
                    and scope["path"] == "/shutdown"
                    and message["type"] == "http.response.body"
                    and not message.get("more_body", False)
                ):
                    await asyncio.sleep(0.45)
                    await send(message)
                    events.append("response-body-sent")
                    return
                await send(message)

            await self.wrapped_app(scope, receive, observed_send)

    handle = start_management_server(DelayedFinalBody(app), port, startup_timeout=2.0)
    try:
        request = Request(
            f"http://127.0.0.1:{port}/shutdown",
            data=b"",
            method="POST",
        )
        with urlopen(request, timeout=2.0) as response:
            assert response.status == 200
            assert response.read()
    finally:
        handle.stop()

    assert events == ["response-body-sent", "shutdown-delivered"]
