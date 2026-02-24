"""Config 클래스 테스트"""

import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def reload_config_with_env(env_vars: dict):
    """환경변수를 설정하고 config 모듈 재로드

    dotenv.load_dotenv를 mock하여 .env 파일 로드를 방지
    """
    with patch.dict(os.environ, env_vars, clear=True):
        with patch("dotenv.load_dotenv"):
            import seosoyoung.config as config_module
            importlib.reload(config_module)
            return config_module


class TestConfigValidation:
    """설정 검증 테스트"""

    def test_validate_missing_slack_bot_token(self):
        """SLACK_BOT_TOKEN 누락 시 ConfigurationError 발생"""
        config_module = reload_config_with_env({})

        with pytest.raises(config_module.ConfigurationError) as exc_info:
            config_module.Config.validate()

        assert "SLACK_BOT_TOKEN" in str(exc_info.value)

    def test_validate_missing_slack_app_token(self):
        """SLACK_APP_TOKEN 누락 시 ConfigurationError 발생"""
        config_module = reload_config_with_env({"SLACK_BOT_TOKEN": "xoxb-test"})

        with pytest.raises(config_module.ConfigurationError) as exc_info:
            config_module.Config.validate()

        assert "SLACK_APP_TOKEN" in str(exc_info.value)

    def test_validate_success_with_required_vars(self):
        """필수 환경변수가 모두 있으면 검증 통과"""
        config_module = reload_config_with_env({
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_APP_TOKEN": "xapp-test"
        })

        # 예외 없이 통과해야 함
        config_module.Config.validate()

    def test_validate_reports_all_missing_vars(self):
        """여러 필수 환경변수 누락 시 모두 보고"""
        config_module = reload_config_with_env({})

        with pytest.raises(config_module.ConfigurationError) as exc_info:
            config_module.Config.validate()

        error_msg = str(exc_info.value)
        assert "SLACK_BOT_TOKEN" in error_msg
        assert "SLACK_APP_TOKEN" in error_msg


class TestConfigConsistency:
    """설정 접근 방식 일관성 테스트"""

    def test_path_methods_exist(self):
        """경로 관련 메서드는 여전히 존재해야 함"""
        from seosoyoung.config import Config

        # 경로 메서드들은 cwd 기준 계산이 필요하므로 메서드로 유지
        assert callable(Config.get_log_path)
        assert callable(Config.get_session_path)
        assert callable(Config.get_glossary_path)
        assert callable(Config.get_narrative_path)
        assert callable(Config.get_search_index_path)
        assert callable(Config.get_web_cache_path)


class TestConfigPaths:
    """경로 설정 테스트"""

    def test_get_log_path_default(self):
        """LOG_PATH 환경변수 없을 때 기본 경로 반환"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("dotenv.load_dotenv"):
                import seosoyoung.config as config_module
                importlib.reload(config_module)

                result = config_module.Config.get_log_path()
                expected = str(Path.cwd() / "logs")
                assert result == expected

    def test_get_log_path_from_env(self):
        """LOG_PATH 환경변수 설정 시 해당 경로 반환"""
        custom_path = "/custom/log/path"
        with patch.dict(os.environ, {"LOG_PATH": custom_path}, clear=True):
            with patch("dotenv.load_dotenv"):
                import seosoyoung.config as config_module
                importlib.reload(config_module)

                result = config_module.Config.get_log_path()
                assert result == custom_path


class TestConfigurationError:
    """ConfigurationError 예외 테스트"""

    def test_configuration_error_exists(self):
        """ConfigurationError 예외 클래스 존재 확인"""
        from seosoyoung.config import ConfigurationError

        assert issubclass(ConfigurationError, Exception)

    def test_configuration_error_with_missing_vars(self):
        """ConfigurationError에 누락된 변수 목록 포함"""
        from seosoyoung.config import ConfigurationError

        error = ConfigurationError(["VAR1", "VAR2"])
        assert "VAR1" in str(error)
        assert "VAR2" in str(error)


class TestConfigBoolParsing:
    """불리언 설정 파싱 테스트"""

    def test_debug_true(self):
        """DEBUG=true 파싱"""
        config_module = reload_config_with_env({"DEBUG": "true"})
        assert config_module.Config.debug is True

    def test_debug_false(self):
        """DEBUG=false 파싱"""
        config_module = reload_config_with_env({"DEBUG": "false"})
        assert config_module.Config.debug is False

    def test_debug_default(self):
        """DEBUG 미설정 시 기본값 False"""
        config_module = reload_config_with_env({})
        assert config_module.Config.debug is False


class TestConfigListParsing:
    """리스트 설정 파싱 테스트"""

    def test_translate_channels_empty(self):
        """TRANSLATE_CHANNELS 미설정 시 빈 리스트"""
        config_module = reload_config_with_env({})
        assert config_module.Config.translate.channels == []

    def test_translate_channels_with_values(self):
        """TRANSLATE_CHANNELS 설정 시 쉼표로 구분된 리스트"""
        config_module = reload_config_with_env({
            "TRANSLATE_CHANNELS": "C123,C456,C789"
        })
        assert config_module.Config.translate.channels == ["C123", "C456", "C789"]

    def test_translate_channels_trims_whitespace(self):
        """TRANSLATE_CHANNELS 값의 공백 제거"""
        config_module = reload_config_with_env({
            "TRANSLATE_CHANNELS": "C123 , C456 , C789"
        })
        assert config_module.Config.translate.channels == ["C123", "C456", "C789"]
