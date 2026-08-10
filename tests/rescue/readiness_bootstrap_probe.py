"""Run the real rescue bootstrap with network boundaries replaced."""

from __future__ import annotations

import json
import os
import sys
from types import ModuleType
from unittest.mock import patch

sys.modules["claude_agent_sdk"] = ModuleType("claude_agent_sdk")

import seosoyoung.rescue.main as bootstrap  # noqa: E402
import seosoyoung.rescue.shutdown as shutdown  # noqa: E402


class FakeClient:
    def auth_test(self) -> dict[str, str]:
        return {"user_id": "U_TEST"}


class FakeSlackApp:
    def __init__(self, **_kwargs) -> None:
        self.client = FakeClient()

    def event(self, _event_name: str):
        return lambda callback: callback


class FakeBot:
    bot_user_id: str | None = None

    def handle_mention(self, *_args, **_kwargs) -> None:
        return None

    def handle_message(self, *_args, **_kwargs) -> None:
        return None


class FakeSocketModeHandler:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def connect(self) -> None:
        print("FUNCTIONAL_INIT_READY", flush=True)


class FakeWaiter:
    def wait(self) -> None:
        return None


with (
    patch.object(shutdown, "create_management_app", return_value=object()),
    patch.object(shutdown, "start_management_server"),
    patch.object(bootstrap, "App", FakeSlackApp),
    patch.object(bootstrap, "RescueBotApp", FakeBot),
    patch.object(bootstrap, "SocketModeHandler", FakeSocketModeHandler),
    patch.object(bootstrap.threading, "Event", return_value=FakeWaiter()),
    patch.object(bootstrap.logger, "info")
    if os.environ.get("SUPPRESS_READINESS_MARKER") == "1"
    else patch.object(bootstrap.logger, "debug"),
):
    bootstrap.main()

print(
    "CONTRACT="
    + json.dumps(
        {
            "marker_hex": bootstrap.READINESS_MARKER.encode().hex(),
            "condition_hex": bootstrap.HANIEL_READY_CONDITION.encode().hex(),
        }
    ),
    file=sys.stdout,
    flush=True,
)
