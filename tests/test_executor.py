"""executor.py 유틸리티 함수 테스트"""

import pytest
from seosoyoung.claude.message_formatter import (
    build_context_usage_bar,
)


class TestBuildContextUsageBar:
    """build_context_usage_bar 함수 테스트"""

    def test_none_usage(self):
        """usage가 None이면 None 반환"""
        assert build_context_usage_bar(None) is None

    def test_empty_usage(self):
        """usage가 빈 dict이면 None 반환"""
        assert build_context_usage_bar({}) is None

    def test_zero_tokens(self):
        """토큰이 0이면 None 반환"""
        assert build_context_usage_bar({"input_tokens": 0}) is None

    def test_cache_creation_tokens(self):
        """cache_creation_input_tokens가 컨텍스트에 포함"""
        # 실제 SDK 응답 패턴: input_tokens=3, cache_creation=35000
        usage = {
            "input_tokens": 3,
            "cache_creation_input_tokens": 35000,
            "cache_read_input_tokens": 0,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "18%" in result  # ~35003 / 200000 = 17.5% -> 18%

    def test_cache_read_tokens(self):
        """cache_read_input_tokens가 컨텍스트에 포함"""
        usage = {
            "input_tokens": 100,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 39900,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "20%" in result  # 40000 / 200000 = 20%

    def test_all_token_types_combined(self):
        """세 종류 토큰 합산"""
        usage = {
            "input_tokens": 10000,
            "cache_creation_input_tokens": 40000,
            "cache_read_input_tokens": 50000,
        }  # 100k / 200k = 50%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "50%" in result
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 10
        assert empty == 10

    def test_full_usage(self):
        """만석 (100%)"""
        usage = {
            "input_tokens": 1000,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 199000,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result
        assert "□" not in result

    def test_over_capacity(self):
        """초과해도 100%로 캡"""
        usage = {
            "input_tokens": 50000,
            "cache_creation_input_tokens": 100000,
            "cache_read_input_tokens": 100000,
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result

    def test_format_structure(self):
        """출력 포맷이 올바른지 확인"""
        usage = {"input_tokens": 60000}  # 30%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert result.startswith("`Context`")
        assert "30%" in result

    def test_only_input_tokens_no_cache(self):
        """cache 키가 없는 경우 input_tokens만으로 계산"""
        usage = {"input_tokens": 40000}  # 20%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "20%" in result

    def test_custom_bar_length(self):
        """bar_length 커스텀"""
        usage = {"input_tokens": 100000}  # 50%
        result = build_context_usage_bar(usage, bar_length=10)
        assert result is not None
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 5
        assert empty == 5

    def test_realistic_sdk_usage(self):
        """실제 SDK 응답 형태의 usage dict"""
        usage = {
            "input_tokens": 3,
            "cache_creation_input_tokens": 35639,
            "cache_read_input_tokens": 0,
            "output_tokens": 11,
            "server_tool_use": {"web_search_requests": 0},
            "service_tier": "standard",
        }
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "18%" in result  # 35642 / 200000 ≈ 17.8% -> 18%
