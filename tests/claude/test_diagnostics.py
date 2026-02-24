"""diagnostics 모듈 테스트"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.slackbot.claude.diagnostics import (
    classify_process_error,
    format_rate_limit_warning,
    send_debug_to_slack,
)


class TestSendDebugToSlack:
    """send_debug_to_slack 콜백 주입 테스트"""

    def test_calls_send_fn(self):
        """send_fn이 전달되면 호출된다"""
        send_fn = MagicMock()
        send_debug_to_slack("C123", "1234.5678", "hello", send_fn=send_fn)
        send_fn.assert_called_once_with("C123", "1234.5678", "hello")

    def test_no_send_fn_no_error(self):
        """send_fn이 None이면 아무 동작 없이 통과"""
        send_debug_to_slack("C123", "1234.5678", "hello", send_fn=None)

    def test_no_send_fn_default(self):
        """send_fn 미지정 시 기본값 None — 오류 없이 통과"""
        send_debug_to_slack("C123", "1234.5678", "hello")

    def test_empty_channel_skips(self):
        """channel이 빈 문자열이면 send_fn 호출 안 함"""
        send_fn = MagicMock()
        send_debug_to_slack("", "1234.5678", "hello", send_fn=send_fn)
        send_fn.assert_not_called()

    def test_empty_thread_ts_skips(self):
        """thread_ts가 빈 문자열이면 send_fn 호출 안 함"""
        send_fn = MagicMock()
        send_debug_to_slack("C123", "", "hello", send_fn=send_fn)
        send_fn.assert_not_called()

    def test_send_fn_exception_logged(self):
        """send_fn에서 예외 발생 시 로그만 남기고 전파하지 않음"""
        send_fn = MagicMock(side_effect=RuntimeError("network error"))
        # 예외가 전파되지 않아야 함
        send_debug_to_slack("C123", "1234.5678", "hello", send_fn=send_fn)
        send_fn.assert_called_once()


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
