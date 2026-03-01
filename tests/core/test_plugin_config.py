"""Tests for core/plugin_config.py — YAML config and registry loading."""

import logging
from pathlib import Path

import pytest
import yaml

from seosoyoung.core.plugin_config import load_plugin_config, load_plugin_registry


@pytest.fixture()
def tmp_yaml(tmp_path):
    """Helper to write YAML content to a temp file and return the path."""

    def _write(content, filename="config.yaml"):
        p = tmp_path / filename
        p.write_text(yaml.dump(content), encoding="utf-8")
        return p

    return _write


class TestLoadPluginConfig:
    def test_loads_valid_yaml(self, tmp_yaml):
        path = tmp_yaml({"key": "value", "nested": {"a": 1}})
        result = load_plugin_config(path)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Plugin config not found"):
            load_plugin_config(tmp_path / "nonexistent.yaml")

    def test_empty_file_returns_empty_dict(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        result = load_plugin_config(path)
        assert result == {}

    def test_accepts_string_path(self, tmp_yaml):
        path = tmp_yaml({"x": 1})
        result = load_plugin_config(str(path))
        assert result == {"x": 1}

    def test_non_dict_content_raises(self, tmp_yaml):
        path = tmp_yaml([1, 2, 3])
        with pytest.raises(TypeError, match="must be a YAML mapping"):
            load_plugin_config(path)


class TestLoadPluginRegistry:
    def test_valid_registry(self, tmp_yaml):
        entries = [
            {"module": "plugins.a", "name": "alpha", "enabled": True},
            {"module": "plugins.b", "name": "beta", "priority": 100},
        ]
        path = tmp_yaml(entries, "plugins.yaml")
        result = load_plugin_registry(path)
        assert len(result) == 2
        assert result[0]["name"] == "alpha"
        assert result[1]["name"] == "beta"

    def test_missing_file_returns_empty_list(self, tmp_path):
        result = load_plugin_registry(tmp_path / "plugins.yaml")
        assert result == []

    def test_non_list_root_returns_empty(self, tmp_yaml, caplog):
        path = tmp_yaml({"not": "a list"}, "plugins.yaml")
        with caplog.at_level(logging.WARNING):
            result = load_plugin_registry(path)
        assert result == []
        assert "root is not a list" in caplog.text

    def test_non_dict_entry_skipped(self, tmp_yaml, caplog):
        entries = [
            {"module": "plugins.a", "name": "alpha"},
            "not a dict",
            {"module": "plugins.b", "name": "beta"},
        ]
        path = tmp_yaml(entries, "plugins.yaml")
        with caplog.at_level(logging.WARNING):
            result = load_plugin_registry(path)
        assert len(result) == 2
        assert "not a dict" in caplog.text

    def test_missing_required_fields_skipped(self, tmp_yaml, caplog):
        entries = [
            {"module": "plugins.a", "name": "alpha"},
            {"module": "plugins.b"},  # missing 'name'
            {"name": "gamma"},  # missing 'module'
            {"description": "no required fields"},  # missing both
        ]
        path = tmp_yaml(entries, "plugins.yaml")
        with caplog.at_level(logging.WARNING):
            result = load_plugin_registry(path)
        assert len(result) == 1
        assert result[0]["name"] == "alpha"

    def test_extra_fields_preserved(self, tmp_yaml):
        entries = [
            {
                "module": "plugins.a",
                "name": "alpha",
                "priority": 100,
                "enabled": True,
                "depends_on": ["beta"],
                "config": {"key": "val"},
            }
        ]
        path = tmp_yaml(entries, "plugins.yaml")
        result = load_plugin_registry(path)
        assert result[0]["priority"] == 100
        assert result[0]["config"] == {"key": "val"}

    def test_empty_list(self, tmp_yaml):
        path = tmp_yaml([], "plugins.yaml")
        result = load_plugin_registry(path)
        assert result == []

    def test_accepts_string_path(self, tmp_yaml):
        path = tmp_yaml(
            [{"module": "plugins.a", "name": "a"}], "plugins.yaml"
        )
        result = load_plugin_registry(str(path))
        assert len(result) == 1
