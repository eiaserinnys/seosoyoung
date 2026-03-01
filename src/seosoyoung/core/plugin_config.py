"""Plugin configuration and registry loading.

Two responsibilities:
  - load_plugin_config:   Load a single plugin's config YAML.
  - load_plugin_registry: Load the plugins.yaml registry file.

No environment variable expansion. plugins.yaml is the single source
of truth for plugin identity, priority, and dependencies.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REQUIRED_REGISTRY_FIELDS = frozenset({"module", "name"})


def load_plugin_config(path: str | Path) -> dict[str, Any]:
    """Load a single plugin's configuration YAML.

    Returns:
        Parsed dict. Empty dict if the file exists but is empty.

    Raises:
        FileNotFoundError: If the file does not exist.
            Caller is responsible for catching and notifying via Slack.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Plugin config not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError(
            f"Plugin config must be a YAML mapping, "
            f"got {type(data).__name__}: {path}"
        )
    return data


def load_plugin_registry(path: str | Path) -> list[dict[str, Any]]:
    """Load the plugin registry (plugins.yaml).

    - File missing     -> empty list (no plugins, not an error).
    - Root not a list  -> empty list + warning.
    - Entry not a dict -> skip + warning.
    - Required fields missing -> skip + warning.
    - ``enabled`` is False -> skip (disabled plugin).

    Required fields per entry: ``module``, ``name``.
    """
    path = Path(path)
    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        logger.warning("plugins.yaml root is not a list, returning empty registry")
        return []

    valid: list[dict[str, Any]] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            logger.warning("plugins.yaml entry %d is not a dict, skipping", i)
            continue

        missing = _REQUIRED_REGISTRY_FIELDS - set(entry.keys())
        if missing:
            logger.warning(
                "plugins.yaml entry %d missing required fields %s, skipping: %s",
                i,
                missing,
                entry,
            )
            continue

        if "enabled" in entry and not entry["enabled"]:
            logger.info("plugins.yaml entry %d disabled, skipping: %s", i, entry["name"])
            continue

        valid.append(entry)

    return valid
