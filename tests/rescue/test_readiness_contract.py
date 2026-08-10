"""Subprocess-observed readiness contract for rescue-bot."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
PROBE = Path(__file__).with_name("readiness_bootstrap_probe.py")


def test_rescue_bootstrap_emits_owned_marker_after_socket_connect() -> None:
    env = {
        **os.environ,
        "RESCUE_SLACK_BOT_TOKEN": "xoxb-readiness-contract",
        "RESCUE_SLACK_APP_TOKEN": "xapp-readiness-contract",
        "RESCUE_SHUTDOWN_PORT": "0",
    }
    result = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    observed = result.stdout + result.stderr

    assert result.returncode == 0, observed
    contract_line = next(
        line for line in result.stdout.splitlines() if line.startswith("CONTRACT=")
    )
    contract = json.loads(contract_line.removeprefix("CONTRACT="))
    assert contract["condition"].startswith("log:")
    assert re.search(contract["condition"].removeprefix("log:"), contract["marker"])
    assert contract["marker"] in observed
    assert result.stdout.index("FUNCTIONAL_INIT_READY") < result.stdout.index(
        contract["marker"]
    )


def test_rescue_workflow_covers_contract_with_minimum_permissions() -> None:
    workflow = (ROOT / ".github/workflows/readiness-contract.yml").read_text(
        encoding="utf-8"
    )
    assert "permissions:\n  contents: read" in workflow
    for path in (
        "pyproject.toml",
        "requirements.txt",
        "src/seosoyoung/rescue/main.py",
        "src/seosoyoung/rescue/readiness.py",
        "tests/rescue/readiness_bootstrap_probe.py",
        "tests/rescue/test_readiness_contract.py",
        ".github/workflows/readiness-contract.yml",
    ):
        assert path in workflow
