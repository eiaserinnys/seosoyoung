"""executor.py 유틸리티 함수 테스트"""

import pytest
from seosoyoung.claude.message_formatter import (
    build_context_usage_bar,
    parse_summary_details,
    strip_summary_details_markers,
)


class TestParseSummaryDetails:
    """parse_summary_details 함수 테스트"""

    def test_no_markers(self):
        """마커가 없는 경우 원본 반환"""
        response = "일반 응답 텍스트입니다."
        summary, details, remainder = parse_summary_details(response)

        assert summary is None
        assert details is None
        assert remainder == response

    def test_summary_only(self):
        """SUMMARY 마커만 있는 경우"""
        response = """<!-- SUMMARY -->
• 요약 첫 번째
• 요약 두 번째
<!-- /SUMMARY -->

추가 내용"""
        summary, details, remainder = parse_summary_details(response)

        assert summary == "• 요약 첫 번째\n• 요약 두 번째"
        assert details is None
        assert remainder == "추가 내용"

    def test_details_only(self):
        """DETAILS 마커만 있는 경우"""
        response = """<!-- DETAILS -->
상세 내용입니다.
여러 줄로 작성.
<!-- /DETAILS -->

나머지"""
        summary, details, remainder = parse_summary_details(response)

        assert summary is None
        assert details == "상세 내용입니다.\n여러 줄로 작성."
        assert remainder == "나머지"

    def test_both_markers(self):
        """SUMMARY와 DETAILS 모두 있는 경우"""
        response = """<!-- SUMMARY -->
• 요약 포인트
<!-- /SUMMARY -->

<!-- DETAILS -->
상세한 설명
<!-- /DETAILS -->"""
        summary, details, remainder = parse_summary_details(response)

        assert summary == "• 요약 포인트"
        assert details == "상세한 설명"
        assert remainder == ""

    def test_with_remainder(self):
        """마커 외 추가 내용이 있는 경우"""
        response = """앞부분

<!-- SUMMARY -->
요약
<!-- /SUMMARY -->

중간

<!-- DETAILS -->
상세
<!-- /DETAILS -->

뒷부분"""
        summary, details, remainder = parse_summary_details(response)

        assert summary == "요약"
        assert details == "상세"
        assert "앞부분" in remainder
        assert "중간" in remainder
        assert "뒷부분" in remainder

    def test_whitespace_handling(self):
        """마커 주변 공백 처리"""
        response = """<!-- SUMMARY -->

   요약 내용

<!-- /SUMMARY -->"""
        summary, details, remainder = parse_summary_details(response)

        assert summary == "요약 내용"
        assert details is None


class TestStripSummaryDetailsMarkers:
    """strip_summary_details_markers 함수 테스트"""

    def test_no_markers(self):
        """마커가 없는 경우 원본 반환"""
        response = "일반 응답입니다."
        result = strip_summary_details_markers(response)

        assert result == response

    def test_removes_summary_markers(self):
        """SUMMARY 마커 제거 (내용 유지)"""
        response = """<!-- SUMMARY -->
요약 내용
<!-- /SUMMARY -->"""
        result = strip_summary_details_markers(response)

        assert "<!-- SUMMARY -->" not in result
        assert "<!-- /SUMMARY -->" not in result
        assert "요약 내용" in result

    def test_removes_details_markers(self):
        """DETAILS 마커 제거 (내용 유지)"""
        response = """<!-- DETAILS -->
상세 내용
<!-- /DETAILS -->"""
        result = strip_summary_details_markers(response)

        assert "<!-- DETAILS -->" not in result
        assert "<!-- /DETAILS -->" not in result
        assert "상세 내용" in result

    def test_removes_all_markers(self):
        """모든 마커 제거"""
        response = """<!-- SUMMARY -->
요약
<!-- /SUMMARY -->

<!-- DETAILS -->
상세
<!-- /DETAILS -->"""
        result = strip_summary_details_markers(response)

        assert "<!-- SUMMARY -->" not in result
        assert "<!-- /SUMMARY -->" not in result
        assert "<!-- DETAILS -->" not in result
        assert "<!-- /DETAILS -->" not in result
        assert "요약" in result
        assert "상세" in result

    def test_cleans_empty_lines(self):
        """빈 줄 정리 (연속된 빈 줄 → 하나로)"""
        response = """<!-- SUMMARY -->
내용
<!-- /SUMMARY -->



추가 텍스트"""
        result = strip_summary_details_markers(response)

        # 연속된 빈 줄 3개 이상이 2개로 줄어듦
        assert "\n\n\n" not in result
        assert "내용" in result
        assert "추가 텍스트" in result

    def test_trims_result(self):
        """결과 양끝 공백 제거"""
        response = """

<!-- SUMMARY -->
내용
<!-- /SUMMARY -->

"""
        result = strip_summary_details_markers(response)

        assert not result.startswith("\n")
        assert not result.endswith("\n")
        assert result == "내용"

    def test_preserves_content_structure(self):
        """내용 구조 유지"""
        response = """<!-- SUMMARY -->
• 포인트 1
• 포인트 2
<!-- /SUMMARY -->

<!-- DETAILS -->
## 제목

코드:
```python
print("hello")
```
<!-- /DETAILS -->"""
        result = strip_summary_details_markers(response)

        assert "• 포인트 1" in result
        assert "• 포인트 2" in result
        assert "## 제목" in result
        assert "```python" in result


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
