"""Installed Slack Bolt marker and workflow path contract for rescue-bot."""

from __future__ import annotations

from importlib.metadata import distribution, version
from pathlib import Path

ROOT = Path(__file__).parents[2]


def _numeric_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def _installed_slack_bolt_source(relative_path: str) -> str:
    package = distribution("slack-bolt")
    return package.locate_file(relative_path).read_text(encoding="utf-8")


def test_rescue_marker_is_owned_by_installed_slack_bolt() -> None:
    bootstrap = (ROOT / "src/seosoyoung/rescue/main.py").read_text(encoding="utf-8")
    builtin_handler = _installed_slack_bolt_source(
        "slack_bolt/adapter/socket_mode/builtin/__init__.py"
    )
    base_handler = _installed_slack_bolt_source(
        "slack_bolt/adapter/socket_mode/base_handler.py"
    )
    utilities = _installed_slack_bolt_source("slack_bolt/util/utils.py")

    assert "handler = SocketModeHandler" in bootstrap
    assert bootstrap.index("handler.start()") > bootstrap.index(
        "handler = SocketModeHandler"
    )
    assert "class SocketModeHandler(BaseSocketModeHandler):" in builtin_handler
    start_body = base_handler.split("    def start(self):", 1)[1]
    connect = start_body.index("self.connect()")
    log_marker = start_body.index("self.app.logger.info(get_boot_message())")
    print_marker = start_body.index("print(get_boot_message())")
    block = start_body.index("Event().wait()")
    assert connect < print_marker < block
    assert connect < log_marker < block
    assert 'return "Bolt app is running!"' in utilities
    assert _numeric_version(version("slack-bolt")) >= (1, 18, 0)


def test_rescue_workflow_covers_every_contract_input() -> None:
    workflow = (ROOT / ".github/workflows/readiness-contract.yml").read_text(
        encoding="utf-8"
    )
    for path in (
        "pyproject.toml",
        "requirements.txt",
        "src/seosoyoung/rescue/main.py",
        "tests/rescue/test_readiness_contract.py",
        ".github/workflows/readiness-contract.yml",
    ):
        assert path in workflow
