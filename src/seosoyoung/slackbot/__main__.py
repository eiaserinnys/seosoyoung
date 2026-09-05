"""Start management HTTP before importing the Slack runtime."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from types import ModuleType

from dotenv import find_dotenv, load_dotenv

from seosoyoung.slackbot.reflect import reflect
from seosoyoung.slackbot.shutdown import (
    ShutdownDispatcher,
    create_management_app,
    start_management_server,
)

RESTART_EXIT_CODE = 43


def _load_runtime() -> ModuleType:
    return importlib.import_module("seosoyoung.slackbot.main")


def run(
    *,
    port: int | None = None,
    runtime_loader: Callable[[], ModuleType] | None = None,
) -> None:
    """Serve management HTTP, then import and start the Slack runtime."""
    load_dotenv(find_dotenv(usecwd=True))
    management_port = port if port is not None else int(os.environ["SHUTDOWN_PORT"])
    load_runtime = runtime_loader or _load_runtime

    dispatcher = ShutdownDispatcher()
    app = create_management_app(reflect, dispatcher)
    handle = start_management_server(app, management_port)
    management_stopped = False

    try:
        if not dispatcher.begin_runtime_import():
            handle.stop()
            management_stopped = True
            raise SystemExit(RESTART_EXIT_CODE)

        runtime = load_runtime()
        dispatcher.bind_shutdown_handler(runtime.handle_management_shutdown)
        if not dispatcher.run_runtime(runtime.main):
            handle.stop()
            management_stopped = True
            return
    finally:
        if not management_stopped:
            handle.stop()


if __name__ == "__main__":
    run()
