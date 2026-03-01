# core/plugin_config.py

> 경로: `seosoyoung/core/plugin_config.py`

## 개요

Plugin configuration and registry loading.

Two responsibilities:
  - load_plugin_config:   Load a single plugin's config YAML.
  - load_plugin_registry: Load the plugins.yaml registry file.

No environment variable expansion. plugins.yaml is the single source
of truth for plugin identity, priority, and dependencies.

## 함수

### `load_plugin_config(path)`
- 위치: 줄 24
- 설명: Load a single plugin's configuration YAML.

Returns:
    Parsed dict. Empty dict if the file exists but is empty.

Raises:
    FileNotFoundError: If the file does not exist.
        Caller is responsible for catching and notifying via Slack.

### `load_plugin_registry(path)`
- 위치: 줄 51
- 설명: Load the plugin registry (plugins.yaml).

- File missing     -> empty list (no plugins, not an error).
- Root not a list  -> empty list + warning.
- Entry not a dict -> skip + warning.
- Required fields missing -> skip + warning.

Required fields per entry: ``module``, ``name``.
