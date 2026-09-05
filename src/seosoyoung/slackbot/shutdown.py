"""Management 서버 (cogito /reflect + /shutdown)

cogito 리플렉션 엔드포인트와 graceful shutdown 엔드포인트를
FastAPI 앱으로 통합하여 제공한다.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import uvicorn
from cogito import Reflector
from cogito.endpoint import mount_cogito
from fastapi import FastAPI

logger = logging.getLogger(__name__)


class ManagementServerStartupError(RuntimeError):
    """Management HTTP server failed before becoming usable."""


@dataclass
class ManagementServerHandle:
    """A running management server and its owning thread."""

    server: uvicorn.Server
    thread: threading.Thread

    def stop(self, timeout: float = 5.0) -> None:
        """Request a graceful stop and fail if the thread does not terminate."""
        if not self.thread.is_alive():
            return
        self.server.should_exit = True
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise RuntimeError("Management server did not stop within the deadline")


class ShutdownDispatcher:
    """Serialize shutdown requests across bootstrap and runtime startup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shutdown_requested = False
        self._delivery_allowed = False
        self._shutdown_delivered = False
        self._runtime_import_started = False
        self._runtime_started = False
        self._handler: Callable[[], None] | None = None

    def request_shutdown(self) -> bool:
        """Record a shutdown synchronously; return true only for the first request."""
        with self._lock:
            if self._shutdown_requested:
                return False
            self._shutdown_requested = True
            return True

    def deliver_shutdown(self) -> None:
        """Deliver a recorded request once the HTTP response may complete."""
        handler = None
        with self._lock:
            self._delivery_allowed = True
            if (
                self._shutdown_requested
                and not self._shutdown_delivered
                and self._handler is not None
            ):
                self._shutdown_delivered = True
                handler = self._handler
        if handler is not None:
            handler()

    def begin_runtime_import(self) -> bool:
        """Claim the import phase unless shutdown already owns the process."""
        with self._lock:
            if self._runtime_import_started:
                raise RuntimeError("Runtime import was already started")
            if self._shutdown_requested:
                return False
            self._runtime_import_started = True
            return True

    def bind_shutdown_handler(self, handler: Callable[[], None]) -> None:
        """Bind the real graceful handler and deliver any mature pending request."""
        deliver_now = False
        with self._lock:
            if not self._runtime_import_started:
                raise RuntimeError("Runtime import must start before handler binding")
            if self._handler is not None:
                raise RuntimeError("Shutdown handler was already bound")
            self._handler = handler
            if (
                self._shutdown_requested
                and self._delivery_allowed
                and not self._shutdown_delivered
            ):
                self._shutdown_delivered = True
                deliver_now = True
        if deliver_now:
            handler()

    def begin_runtime(self) -> bool:
        """Claim user-work acceptance unless a shutdown request won the race."""
        with self._lock:
            if self._handler is None:
                raise RuntimeError("Shutdown handler must be bound before runtime start")
            if self._runtime_started:
                raise RuntimeError("Runtime was already started")
            if self._shutdown_requested:
                return False
            self._runtime_started = True
            return True


def create_management_app(
    reflector: Reflector,
    shutdown_dispatcher: ShutdownDispatcher,
) -> FastAPI:
    """cogito /reflect + /shutdown 을 제공하는 FastAPI 앱을 생성한다."""
    app = FastAPI()
    mount_cogito(app, reflector)

    @app.post("/shutdown")
    async def shutdown():
        first_request = shutdown_dispatcher.request_shutdown()
        if first_request:
            delivery = threading.Timer(0.1, shutdown_dispatcher.deliver_shutdown)
            delivery.daemon = True
            delivery.start()
        return {"status": "shutting down"}

    return app


def _raise_startup_failure(
    message: str,
    failure: list[BaseException],
) -> None:
    error = ManagementServerStartupError(message)
    if failure:
        raise error from failure[0]
    raise error


def start_management_server(
    app: FastAPI,
    port: int,
    host: str = "127.0.0.1",
    *,
    startup_timeout: float = 10.0,
) -> ManagementServerHandle:
    """Start Uvicorn and return only after the real /reflect handler answers."""
    if startup_timeout <= 0:
        raise ValueError("startup_timeout must be positive")

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    finished = threading.Event()
    failure: list[BaseException] = []

    def run_server() -> None:
        try:
            server.run()
        except BaseException as exc:
            failure.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(
        target=run_server,
        name="slackbot-management",
        daemon=True,
    )
    handle = ManagementServerHandle(server=server, thread=thread)
    thread.start()

    deadline = time.monotonic() + startup_timeout
    last_probe_error: BaseException | None = None
    while time.monotonic() < deadline:
        if finished.is_set() or not thread.is_alive():
            _raise_startup_failure(
                "Management server exited before readiness",
                failure,
            )

        if server.started:
            remaining = deadline - time.monotonic()
            try:
                with urlopen(
                    f"http://{host}:{port}/reflect",
                    timeout=max(0.01, min(0.2, remaining)),
                ) as response:
                    if response.status == 200:
                        if not thread.is_alive():
                            _raise_startup_failure(
                                "Management server exited after readiness probe",
                                failure,
                            )
                        logger.info("Management server ready on %s:%d", host, port)
                        return handle
                    last_probe_error = RuntimeError(
                        f"/reflect returned HTTP {response.status}"
                    )
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                last_probe_error = exc

        finished.wait(min(0.02, max(0.0, deadline - time.monotonic())))

    server.should_exit = True
    thread.join(min(1.0, startup_timeout))
    failure_message = "Management server /reflect did not become ready before deadline"
    if last_probe_error is not None:
        failure.append(last_probe_error)
    _raise_startup_failure(failure_message, failure)
