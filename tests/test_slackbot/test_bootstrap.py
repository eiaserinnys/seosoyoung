"""Slack bot management bootstrap contract tests."""

from __future__ import annotations

import logging
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.request import urlopen

import pytest
from fastapi import FastAPI

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
        dispatcher.deliver_shutdown()

        assert delivered == ["shutdown"]
        assert dispatcher.begin_runtime() is False

    def test_request_between_handler_bind_and_runtime_start_blocks_runtime(self):
        dispatcher = ShutdownDispatcher()
        delivered = []
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))

        dispatcher.request_shutdown()
        dispatcher.deliver_shutdown()

        assert dispatcher.begin_runtime() is False
        assert delivered == ["shutdown"]

    def test_request_after_runtime_start_is_delivered_once(self):
        dispatcher = ShutdownDispatcher()
        delivered = []
        assert dispatcher.begin_runtime_import() is True
        dispatcher.bind_shutdown_handler(lambda: delivered.append("shutdown"))
        assert dispatcher.begin_runtime() is True

        dispatcher.request_shutdown()
        dispatcher.request_shutdown()
        dispatcher.deliver_shutdown()
        dispatcher.deliver_shutdown()

        assert delivered == ["shutdown"]


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

    bootstrap.run(port=3106, runtime_loader=runtime_loader)

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
        captured["dispatcher"].deliver_shutdown()
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


def test_management_handler_uses_existing_graceful_shutdown(monkeypatch):
    from seosoyoung.slackbot import main as runtime

    graceful_shutdown = Mock()
    monkeypatch.setattr(runtime, "_shutdown_with_session_wait", graceful_shutdown)

    runtime.handle_management_shutdown()

    graceful_shutdown.assert_called_once_with(
        runtime.RestartType.RESTART,
        "HTTP /shutdown",
    )


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
            main=lambda: events.append("runtime-start"),
        )

    bootstrap.run(port=port, runtime_loader=load_runtime)

    assert events == [("reflect", 200), "runtime-import", "runtime-start"]
