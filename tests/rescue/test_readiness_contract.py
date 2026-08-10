"""Subprocess-observed readiness contract for rescue-bot."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PROBE = Path(__file__).with_name("readiness_bootstrap_probe.py")
CONTRACT = ROOT / "readiness-contract.json"


def _run_probe(*, suppress_marker: bool = False):
    env = {
        **os.environ,
        "RESCUE_SLACK_BOT_TOKEN": "xoxb-readiness-contract",
        "RESCUE_SLACK_APP_TOKEN": "xapp-readiness-contract",
        "RESCUE_SHUTDOWN_PORT": "0",
    }
    env.pop("SUPPRESS_READINESS_MARKER", None)
    if suppress_marker:
        env["SUPPRESS_READINESS_MARKER"] = "1"
    result = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result


def _assert_contract(result) -> None:
    observed = result.stdout + result.stderr
    assert result.returncode == 0, observed
    contract_line = next(
        line for line in result.stdout.splitlines() if line.startswith("CONTRACT=")
    )
    contract = json.loads(contract_line.removeprefix("CONTRACT="))
    condition = bytes.fromhex(contract["condition_hex"]).decode()
    marker = bytes.fromhex(contract["marker_hex"]).decode()
    assert condition.startswith("log:")
    assert re.search(condition.removeprefix("log:"), marker)
    assert marker in observed
    assert "FUNCTIONAL_INIT_READY" in result.stdout
    assert marker in result.stdout
    assert result.stdout.index("FUNCTIONAL_INIT_READY") < result.stdout.index(marker)


def test_rescue_bootstrap_emits_owned_marker_after_socket_connect() -> None:
    _assert_contract(_run_probe())


def test_rescue_publishes_machine_readable_readiness_contract() -> None:
    from seosoyoung.rescue.readiness import HANIEL_READY_CONDITION, READINESS_MARKER

    assert json.loads(CONTRACT.read_text(encoding="utf-8")) == {
        "schema_version": "haniel.readiness-contract.v1",
        "service": "rescue-bot",
        "marker": READINESS_MARKER,
        "ready": HANIEL_READY_CONDITION,
    }


def test_rescue_contract_fails_when_product_marker_is_suppressed() -> None:
    with pytest.raises(AssertionError):
        _assert_contract(_run_probe(suppress_marker=True))


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
        "readiness-contract.json",
    ):
        assert path in workflow
