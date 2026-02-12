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
        assert build_context_usage_bar({"input_tokens": 0, "output_tokens": 0}) is None

    def test_low_usage(self):
        """낮은 사용량 (10%)"""
        usage = {"input_tokens": 15000, "output_tokens": 5000}  # 20k / 200k = 10%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "10%" in result
        assert "■■" in result
        assert "□" in result

    def test_half_usage(self):
        """절반 사용량 (50%)"""
        usage = {"input_tokens": 80000, "output_tokens": 20000}  # 100k / 200k = 50%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "50%" in result
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 10
        assert empty == 10

    def test_full_usage(self):
        """거의 만석 (100%)"""
        usage = {"input_tokens": 180000, "output_tokens": 20000}  # 200k / 200k = 100%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result
        assert "□" not in result

    def test_over_capacity(self):
        """초과해도 100%로 캡"""
        usage = {"input_tokens": 200000, "output_tokens": 50000}  # 250k / 200k > 100%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "100%" in result

    def test_format_structure(self):
        """출력 포맷이 올바른지 확인"""
        usage = {"input_tokens": 60000, "output_tokens": 0}  # 30%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert result.startswith("`Context`")
        assert "30%" in result

    def test_only_input_tokens(self):
        """input_tokens만 있는 경우"""
        usage = {"input_tokens": 40000}  # 20%
        result = build_context_usage_bar(usage)
        assert result is not None
        assert "20%" in result

    def test_custom_bar_length(self):
        """bar_length 커스텀"""
        usage = {"input_tokens": 100000, "output_tokens": 0}  # 50%
        result = build_context_usage_bar(usage, bar_length=10)
        assert result is not None
        filled = result.count("■")
        empty = result.count("□")
        assert filled == 5
        assert empty == 5
