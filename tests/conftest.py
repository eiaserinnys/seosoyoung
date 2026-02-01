"""Pytest 설정"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
from dotenv import load_dotenv

# .env 로드 (RECALL_API_KEY 등)
load_dotenv()

# 테스트 환경 변수 설정
os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-token"
os.environ["SLACK_APP_TOKEN"] = "xapp-test-token"
# ANTHROPIC_API_KEY는 설정하지 않음 (CLI 로그인 세션 사용)
# os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key"

# slack_bolt를 mock하여 실제 API 호출 방지
mock_app = MagicMock()
mock_app.event = MagicMock(return_value=lambda f: f)  # 데코레이터 mock

sys.modules["slack_bolt"] = MagicMock()
sys.modules["slack_bolt"].App = MagicMock(return_value=mock_app)
sys.modules["slack_bolt.adapter.socket_mode"] = MagicMock()

# src 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
