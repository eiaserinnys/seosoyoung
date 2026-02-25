"""diagnostics 모듈 테스트"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.slackbot.claude.diagnostics import (
    classify_process_error,
    format_rate_limit_warning,
)


class TestClassifyProcessError:
    """ProcessError 분류 테스트"""

    def _make_error(self, exit_code=1, stderr="", message=""):
        """ProcessError 모사 객체 생성"""
        err = type("ProcessError", (), {
            "exit_code": exit_code,
            "stderr": stderr,
            "__str__": lambda self: message,
        })()
        return err

    def test_rate_limit(self):
        msg = classify_process_error(self._make_error(message="rate limit exceeded"))
        assert "사용량 제한" in msg

    def test_auth_error(self):
        msg = classify_process_error(self._make_error(message="unauthorized"))
        assert "인증" in msg

    def test_network_error(self):
        msg = classify_process_error(self._make_error(stderr="connection refused"))
        assert "네트워크" in msg

    def test_generic_exit_1(self):
        msg = classify_process_error(self._make_error(exit_code=1, message="unknown"))
        assert "비정상 종료" in msg

    def test_other_exit_code(self):
        msg = classify_process_error(self._make_error(exit_code=2, message="some error"))
        assert "exit code: 2" in msg


class TestFormatRateLimitWarning:
    """rate limit warning 포맷 테스트"""

    def test_seven_day(self):
        result = format_rate_limit_warning({"rateLimitType": "seven_day", "utilization": 0.51})
        assert "주간" in result
        assert "51%" in result

    def test_five_hour(self):
        result = format_rate_limit_warning({"rateLimitType": "five_hour", "utilization": 0.8})
        assert "5시간" in result
        assert "80%" in result

    def test_unknown_type(self):
        result = format_rate_limit_warning({"rateLimitType": "custom", "utilization": 0.3})
        assert "custom" in result
        assert "30%" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
