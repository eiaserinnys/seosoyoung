"""Pytest 설정"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
from dotenv import load_dotenv
import pytest

# .env 로드 (RECALL_API_KEY 등)
load_dotenv()

# 테스트 환경 변수 설정
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test-token")
os.environ.setdefault("OPERATOR_USER_ID", "U00000000")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GEMINI_MODEL", "gemini-3-pro-image-preview")
os.environ.setdefault("SEOSOYOUNG_SOUL_URL", "http://localhost:4105")
os.environ.setdefault("SEOSOYOUNG_SOUL_TOKEN", "test-token")
os.environ.setdefault("CREDENTIAL_ALERT_CHANNEL", "")
os.environ.setdefault("EXECUTE_EMOJI", "rocket")
os.environ.setdefault("EMOJI_TRANSLATE_PROGRESS", "hourglass_flowing_sand")
os.environ.setdefault("EMOJI_TRANSLATE_DONE", "ssy-happy")
os.environ.setdefault("EMOJI_TEXT_SESSION_START", ":rocket:")
os.environ.setdefault("EMOJI_TEXT_LTM_INJECT", ":brain:")
os.environ.setdefault("EMOJI_TEXT_NEW_OBS_INJECT", ":eye:")
os.environ.setdefault("EMOJI_TEXT_SESSION_OBS_INJECT", ":thread:")
os.environ.setdefault("EMOJI_TEXT_CHANNEL_OBS_INJECT", ":channel:")
os.environ.setdefault("EMOJI_TEXT_RESTART_TROUBLE", ":warning:")
os.environ.setdefault("EMOJI_TEXT_OBS_COMPLETE", ":white_check_mark:")
os.environ.setdefault("EMOJI_TEXT_INTERVENTION_ERROR", ":x:")
# ANTHROPIC_API_KEY는 설정하지 않음 (CLI 로그인 세션 사용)
# os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"

# slack_bolt를 mock하여 실제 API 호출 방지
mock_app = MagicMock()
mock_app.event = MagicMock(return_value=lambda f: f)  # 데코레이터 mock

sys.modules["slack_bolt"] = MagicMock()
sys.modules["slack_bolt"].App = MagicMock(return_value=mock_app)
sys.modules["slack_bolt.adapter.socket_mode"] = MagicMock()

# cogito mock (설치되지 않은 경우)
# Reflector를 실제 클래스로 정의해야 SupervisorReflector(Reflector) 상속이 올바르게 동작한다.
# MagicMock 인스턴스를 base class로 사용하면 subclass의 metaclass가 MagicMock이 되어
# 메서드(start 등)가 MagicMock으로 교체되는 문제가 생긴다.
class _MockReflector:
    """테스트용 cogito.Reflector stub."""

    def __init__(self, **kwargs):
        pass

    def capability(self, **kwargs):
        return lambda f: f

    def collect_capabilities(self):
        return []

    def get_level3(self) -> dict:
        return {}

    def get_sources(self):
        return []


mock_cogito = MagicMock()
mock_cogito.Reflector = _MockReflector
sys.modules["cogito"] = mock_cogito

# src 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pytest_collection_modifyitems(config, items):
    """integration 마커가 붙은 테스트는 -m integration 옵션 없이 실행 시 자동 스킵"""
    if config.getoption("-m", default="") == "integration":
        return
    skip_integration = pytest.mark.skip(reason="통합 테스트: pytest -m integration 으로 실행")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
