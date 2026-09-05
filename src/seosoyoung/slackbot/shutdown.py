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
from fastapi.responses import JSONResponse
from starlette.types import Receive, Scope, Send

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
        self._response_completed = False
        self._delivery_in_progress = False
        self._shutdown_delivered = False
        self._delivery_error: BaseException | None = None
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

    @property
    def delivery_failed(self) -> bool:
        """Return whether the single shutdown callback attempt failed."""
        with self._lock:
            return self._delivery_error is not None

    def _deliver_shutdown_if_ready(self) -> None:
        handler: Callable[[], None] | None = None
        with self._lock:
            if self._delivery_error is not None:
                raise self._delivery_error
            if (
                self._shutdown_requested
                and self._response_completed
                and not self._shutdown_delivered
                and not self._delivery_in_progress
                and self._handler is not None
            ):
                self._delivery_in_progress = True
                handler = self._handler

        if handler is None:
            return

        try:
            handler()
        except BaseException as exc:
            with self._lock:
                self._delivery_in_progress = False
                self._delivery_error = exc
            raise
        else:
            with self._lock:
                self._delivery_in_progress = False
                self._shutdown_delivered = True

    def complete_shutdown_response(self) -> None:
        """Mark the final ASGI response body sent, then deliver once if possible."""
        with self._lock:
            self._response_completed = True
        self._deliver_shutdown_if_ready()

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
        with self._lock:
            if not self._runtime_import_started:
                raise RuntimeError("Runtime import must start before handler binding")
            if self._handler is not None:
                raise RuntimeError("Shutdown handler was already bound")
            self._handler = handler
        self._deliver_shutdown_if_ready()

    def run_runtime(
        self,
        runtime_main: Callable[[Callable[[], None]], None],
    ) -> bool:
        """Invoke runtime with an atomic entry handoff to its first instruction."""
        self._lock.acquire()
        lock_owned = True
        runtime_entered = False

        def mark_runtime_entered() -> None:
            nonlocal lock_owned, runtime_entered
            if runtime_entered or not lock_owned:
                raise RuntimeError("Runtime entry was already confirmed")
            self._runtime_started = True
            runtime_entered = True
            lock_owned = False
            self._lock.release()

        try:
            if self._handler is None:
                raise RuntimeError("Shutdown handler must be bound before runtime start")
            if self._runtime_started:
                raise RuntimeError("Runtime was already started")
            if self._shutdown_requested:
                return False

            runtime_main(mark_runtime_entered)
            if not runtime_entered:
                raise RuntimeError("Runtime did not confirm entry")
            return True
        finally:
            if lock_owned:
                self._lock.release()


class _ShutdownResponse(JSONResponse):
    """Complete the accepted shutdown after success or terminal send failure."""

    def __init__(self, on_response_finished: Callable[[], None] | None) -> None:
        super().__init__({"status": "shutting down"})
        self._on_response_finished = on_response_finished

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except BaseException:
            if self._on_response_finished is not None:
                self._on_response_finished()
            raise
        else:
            if self._on_response_finished is not None:
                self._on_response_finished()


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
        if shutdown_dispatcher.delivery_failed:
            return JSONResponse(
                {
                    "status": "shutdown_failed",
                    "code": "shutdown_callback_failed",
                },
                status_code=500,
            )
        return _ShutdownResponse(
            shutdown_dispatcher.complete_shutdown_response if first_request else None
        )

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

    failure_message = "Management server /reflect did not become ready before deadline"
    if last_probe_error is not None:
        failure.append(last_probe_error)
    try:
        handle.stop()
    except RuntimeError as exc:
        failure.insert(0, exc)
        failure_message += "; cooperative cleanup also failed"
    _raise_startup_failure(failure_message, failure)
