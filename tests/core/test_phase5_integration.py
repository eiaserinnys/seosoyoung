"""Phase 5 통합 테스트.

플러그인 아키텍처 마이그레이션 완료 후 검증:
- Config에서 플러그인 설정이 제거되었는지
- 플러그인 코드가 Config/os.environ에 의존하지 않는지
- 구 코드 디렉토리가 삭제되었는지
- CLI 명령어 핸들러가 동작하는지
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, AsyncMock

import pytest

from seosoyoung.slackbot.config import Config


# -- Config 슬림 다운 검증 --------------------------------------------------


class TestConfigSlimDown:
    """Config에서 플러그인 설정이 완전히 제거되었는지 검증."""

    def test_no_trello_config(self):
        """TrelloConfig가 Config에서 제거됨."""
        assert not hasattr(Config, "trello"), "Config.trello가 아직 존재합니다"

    def test_no_translate_config(self):
        """TranslateConfig가 Config에서 제거됨."""
        assert not hasattr(Config, "translate"), "Config.translate가 아직 존재합니다"

    def test_no_om_config(self):
        """OMConfig가 Config에서 제거됨."""
        assert not hasattr(Config, "om"), "Config.om이 아직 존재합니다"

    def test_no_channel_observer_config(self):
        """ChannelObserverConfig가 Config에서 제거됨."""
        assert not hasattr(Config, "channel_observer"), "Config.channel_observer가 아직 존재합니다"

    def test_core_configs_remain(self):
        """코어 설정은 유지됨."""
        assert hasattr(Config, "slack")
        assert hasattr(Config, "auth")
        assert hasattr(Config, "gemini")
        assert hasattr(Config, "claude")
        assert hasattr(Config, "emoji")

    def test_notify_channel_on_slack(self):
        """notify_channel이 SlackConfig에 존재."""
        assert hasattr(Config.slack, "notify_channel")


# -- 구 코드 디렉토리 삭제 검증 -----------------------------------------------


class TestOldCodeRemoved:
    """구 핸들러 코드가 삭제되었는지 검증."""

    def _get_src_dir(self) -> Path:
        """seosoyoung 소스 디렉토리 경로를 반환."""
        config_mod = importlib.import_module("seosoyoung.slackbot.config")
        return Path(config_mod.__file__).parent

    def test_old_trello_dir_removed(self):
        """slackbot/trello/ 디렉토리가 삭제됨."""
        src_dir = self._get_src_dir()
        old_trello = src_dir / "trello"
        assert not old_trello.exists(), f"구 trello 디렉토리가 남아있습니다: {old_trello}"

    def test_old_translator_dir_removed(self):
        """slackbot/translator/ 디렉토리가 삭제됨."""
        src_dir = self._get_src_dir()
        old_translator = src_dir / "translator"
        assert not old_translator.exists(), f"구 translator 디렉토리가 남아있습니다: {old_translator}"

    def test_plugin_trello_exists(self):
        """plugins/trello/ 디렉토리는 존재함."""
        src_dir = self._get_src_dir()
        plugin_trello = src_dir / "plugins" / "trello"
        assert plugin_trello.exists(), "plugins/trello/ 디렉토리가 없습니다"

    def test_plugin_translate_exists(self):
        """plugins/translate/ 디렉토리는 존재함."""
        src_dir = self._get_src_dir()
        plugin_translate = src_dir / "plugins" / "translate"
        assert plugin_translate.exists(), "plugins/translate/ 디렉토리가 없습니다"


# -- 플러그인 코드 의존성 감사 ------------------------------------------------


class TestPluginNoDependencyOnConfig:
    """플러그인 코드가 Config 싱글톤이나 os.environ을 참조하지 않는지 검증."""

    @staticmethod
    def _get_plugin_source_files() -> list[Path]:
        """plugins/ 하위 모든 .py 파일을 반환."""
        config_mod = importlib.import_module("seosoyoung.slackbot.config")
        plugins_dir = Path(config_mod.__file__).parent / "plugins"
        return list(plugins_dir.rglob("*.py"))

    @staticmethod
    def _get_core_source_files() -> list[Path]:
        """core/ 하위 모든 .py 파일을 반환."""
        core_mod = importlib.import_module("seosoyoung.core.plugin")
        core_dir = Path(core_mod.__file__).parent
        return list(core_dir.rglob("*.py"))

    def test_no_config_import_in_plugins(self):
        """플러그인 코드에 Config 싱글톤 import가 없음."""
        violations = []
        for py_file in self._get_plugin_source_files():
            content = py_file.read_text(encoding="utf-8")
            if "from seosoyoung.slackbot.config import" in content:
                violations.append(str(py_file))
        assert not violations, f"Config import 발견: {violations}"

    def test_no_os_getenv_in_plugins(self):
        """플러그인 코드에 os.getenv 호출이 없음."""
        violations = []
        for py_file in self._get_plugin_source_files():
            content = py_file.read_text(encoding="utf-8")
            if "os.getenv" in content or "os.environ" in content:
                violations.append(str(py_file))
        assert not violations, f"os.getenv/os.environ 발견: {violations}"

    def test_no_config_import_in_core(self):
        """코어 코드에 Config 싱글톤 import가 없음."""
        violations = []
        for py_file in self._get_core_source_files():
            content = py_file.read_text(encoding="utf-8")
            if "from seosoyoung.slackbot.config import" in content:
                violations.append(str(py_file))
        assert not violations, f"Config import 발견 (core): {violations}"


# -- CLI 명령어 핸들러 테스트 --------------------------------------------------


class TestPluginsCommand:
    """plugins 명령어 핸들러 테스트."""

    def _make_say(self):
        return MagicMock()

    def _make_plugin_manager(self):
        from seosoyoung.core.plugin import Plugin, PluginMeta

        class DummyPlugin(Plugin):
            meta = PluginMeta(name="dummy", version="0.1.0", description="Test plugin")

            async def on_load(self, config):
                pass

            async def on_unload(self):
                pass

        pm = MagicMock()
        pm.plugins = {"dummy": DummyPlugin()}
        pm._priorities = {"dummy": 50}
        return pm

    def test_plugins_list(self):
        from seosoyoung.slackbot.handlers.commands import handle_plugins

        say = self._make_say()
        pm = self._make_plugin_manager()
        handle_plugins(
            command="plugins list",
            say=say,
            ts="1234",
            user_id="U123",
            client=MagicMock(),
            check_permission=lambda *a: True,
            plugin_manager=pm,
        )
        say.assert_called_once()
        text = say.call_args[1]["text"]
        assert "dummy" in text
        assert "v0.1.0" in text

    def test_plugins_no_manager(self):
        from seosoyoung.slackbot.handlers.commands import handle_plugins

        say = self._make_say()
        handle_plugins(
            command="plugins list",
            say=say,
            ts="1234",
            user_id="U123",
            client=MagicMock(),
            check_permission=lambda *a: True,
            plugin_manager=None,
        )
        say.assert_called_once()
        assert "초기화" in say.call_args[1]["text"]

    def test_plugins_permission_denied(self):
        from seosoyoung.slackbot.handlers.commands import handle_plugins

        say = self._make_say()
        handle_plugins(
            command="plugins list",
            say=say,
            ts="1234",
            user_id="U123",
            client=MagicMock(),
            check_permission=lambda *a: False,
            plugin_manager=self._make_plugin_manager(),
        )
        say.assert_called_once()
        assert "관리자" in say.call_args[1]["text"]


# -- TranslatePlugin public API 테스트 ----------------------------------------


class TestTranslatePluginPublicAPI:
    """TranslatePlugin.translate_text() 메서드 테스트."""

    def test_translate_text_method_exists(self):
        """translate_text() 메서드가 존재하는지 확인."""
        from seosoyoung.slackbot.plugins.translate.plugin import TranslatePlugin
        assert hasattr(TranslatePlugin, "translate_text")
        assert callable(getattr(TranslatePlugin, "translate_text"))
