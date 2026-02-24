"""보안 레이어 테스트

보안 검사 코드가 제거되어 테스트도 대부분 제거되었습니다.
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.claude.security import SecurityError


class TestSecurityError:
    """SecurityError 테스트"""

    def test_security_error_is_exception(self):
        """SecurityError가 Exception을 상속하는지 확인"""
        assert issubclass(SecurityError, Exception)

    def test_security_error_message(self):
        """SecurityError 메시지 테스트"""
        error = SecurityError("테스트 에러")
        assert str(error) == "테스트 에러"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
