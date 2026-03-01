"""용어집 모듈 테스트"""

import pytest
from unittest.mock import patch, mock_open

from seosoyoung.slackbot.plugins.translate.glossary import (
    _extract_name_pair,
    _extract_short_names,
    get_glossary_entries,
    find_relevant_terms,
    find_relevant_terms_v2,
    GlossaryMatchResult,
    clear_cache,
)


# 테스트용 샘플 YAML 데이터 (glossary.yaml 실제 구조: name: {kr, en})
SAMPLE_GLOSSARY_YAML = """
id: glossary

main_characters:
  items:
    - name:
        kr: 펜릭스 헤이븐
        en: Fenrix Haven
    - name:
        kr: 성채의 수호자, 아리엘라 애시우드
        en: Ariella Ashwood, the Guardian of the Sanctuary

main_places:
  items:
    - name:
        kr: 망각의 성채
        en: The Sanctuary of Oblivion
"""


class TestExtractNamePair:
    """이름 쌍 추출 테스트"""

    def test_extract_valid_pair(self):
        """유효한 이름 쌍 추출 (name: {kr, en} 구조)"""
        item = {
            "name": {"kr": "펜릭스", "en": "Fenrix"},
        }
        result = _extract_name_pair(item)
        assert result == ("펜릭스", "Fenrix")

    def test_extract_missing_name(self):
        """name 키 누락"""
        item = {"description": {"kr": "주인공", "en": "protagonist"}}
        result = _extract_name_pair(item)
        assert result is None

    def test_extract_missing_kr(self):
        """name.kr 누락"""
        item = {"name": {"en": "Fenrix"}}
        result = _extract_name_pair(item)
        assert result is None

    def test_extract_missing_en(self):
        """name.en 누락"""
        item = {"name": {"kr": "펜릭스"}}
        result = _extract_name_pair(item)
        assert result is None

    def test_extract_empty_item(self):
        """빈 항목"""
        result = _extract_name_pair({})
        assert result is None

    def test_extract_name_not_dict(self):
        """name이 dict가 아닌 경우"""
        item = {"name": "펜릭스"}
        result = _extract_name_pair(item)
        assert result is None


class TestExtractShortNames:
    """짧은 이름 추출 테스트"""

    def test_simple_name(self):
        """단순 이름"""
        result = _extract_short_names("펜릭스")
        assert "펜릭스" in result

    def test_comma_separated(self):
        """쉼표로 분리된 이름"""
        result = _extract_short_names("불사의 악마 사냥꾼, 펜릭스 헤이븐")
        assert "불사의 악마 사냥꾼, 펜릭스 헤이븐" in result
        assert "불사의 악마 사냥꾼" in result
        assert "펜릭스 헤이븐" in result

    def test_parenthesis_removal(self):
        """괄호 제거"""
        result = _extract_short_names("(눈 먼 정의의 천사) 칼리엘")
        assert "(눈 먼 정의의 천사) 칼리엘" in result
        assert "칼리엘" in result

    def test_first_word_extraction(self):
        """이름 성 패턴에서 첫 단어 추출"""
        result = _extract_short_names("펜릭스 헤이븐")
        assert "펜릭스 헤이븐" in result
        assert "펜릭스" in result


class TestFindRelevantTerms:
    """관련 용어 찾기 테스트 (새 알고리즘)"""

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_find_korean_terms(self, mock_extract, mock_entries, mock_index):
        """한국어 텍스트에서 용어 찾기"""
        mock_entries.return_value = (
            ("펜릭스", "Fenrix"),
            ("아리엘라", "Ariella"),
        )
        mock_index.return_value = (
            {"펜릭스": [0], "아리엘라": [1]},
            {"Fenrix": [0], "Ariella": [1]}
        )
        mock_extract.return_value = ["펜릭스", "아리엘라"]

        text = "펜릭스가 아리엘라에게 말했다."
        result = find_relevant_terms(text, "ko", glossary_path="")

        assert len(result) == 2
        assert ("펜릭스", "Fenrix") in result
        assert ("아리엘라", "Ariella") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_english_words")
    def test_find_english_terms(self, mock_extract, mock_entries, mock_index):
        """영어 텍스트에서 용어 찾기"""
        mock_entries.return_value = (
            ("펜릭스", "Fenrix"),
            ("아리엘라", "Ariella"),
        )
        mock_index.return_value = (
            {"펜릭스": [0], "아리엘라": [1]},
            {"Fenrix": [0], "Ariella": [1]}
        )
        mock_extract.return_value = ["Fenrix", "Ariella"]

        text = "Fenrix spoke to Ariella."
        result = find_relevant_terms(text, "en", glossary_path="")

        assert len(result) == 2
        assert ("Fenrix", "펜릭스") in result
        assert ("Ariella", "아리엘라") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_english_words")
    def test_find_no_matching_terms(self, mock_extract, mock_entries, mock_index):
        """매칭되는 용어 없음"""
        mock_entries.return_value = (("펜릭스", "Fenrix"),)
        mock_index.return_value = ({"펜릭스": [0]}, {"Fenrix": [0]})
        mock_extract.return_value = ["Hello", "world"]

        text = "Hello world"
        result = find_relevant_terms(text, "en", glossary_path="")

        assert len(result) == 0

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_no_duplicate_matches(self, mock_extract, mock_entries, mock_index):
        """중복 매칭 방지"""
        mock_entries.return_value = (("펜릭스", "Fenrix"),)
        mock_index.return_value = ({"펜릭스": [0]}, {"Fenrix": [0]})
        mock_extract.return_value = ["펜릭스", "펜릭스"]

        text = "펜릭스가 펜릭스에게 말했다."
        result = find_relevant_terms(text, "ko", glossary_path="")

        # 같은 용어는 한 번만 포함
        assert len(result) == 1
        assert ("펜릭스", "Fenrix") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_fuzzy_match_typo(self, mock_extract, mock_entries, mock_index):
        """오타가 있는 용어 퍼지 매칭"""
        mock_entries.return_value = (
            ("아리엘라", "Ariella"),
            ("펜릭스 헤이븐", "Fenrix Haven"),
        )
        mock_index.return_value = (
            {"아리엘라": [0], "펜릭스 헤이븐": [1], "펜릭스": [1], "헤이븐": [1]},
            {"Ariella": [0], "Fenrix Haven": [1], "Fenrix": [1], "Haven": [1]}
        )
        mock_extract.return_value = ["아리엘나"]  # 오타 (4자 중 1자 다름 = 75%)

        text = "아리엘나가 말했다."
        # 75% 유사도이므로 70% 임계값 사용
        result = find_relevant_terms(text, "ko", fuzzy_threshold=70, glossary_path="")

        # 퍼지 매칭으로 유사한 용어 찾아야 함
        assert len(result) >= 1
        assert ("아리엘라", "Ariella") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_english_words")
    def test_fuzzy_match_english_typo(self, mock_extract, mock_entries, mock_index):
        """영어 오타 퍼지 매칭"""
        mock_entries.return_value = (("아리엘라", "Ariella"),)
        mock_index.return_value = ({"아리엘라": [0]}, {"Ariella": [0]})
        mock_extract.return_value = ["Ariela"]  # 오타

        text = "Ariela spoke quietly."
        result = find_relevant_terms(text, "en", fuzzy_threshold=80, glossary_path="")

        assert len(result) >= 1
        assert ("Ariella", "아리엘라") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_fuzzy_match_partial_name(self, mock_extract, mock_entries, mock_index):
        """부분 이름 퍼지 매칭"""
        mock_entries.return_value = (("망각의 성채", "The Sanctuary of Oblivion"),)
        mock_index.return_value = (
            {"망각의 성채": [0], "망각의": [0], "성채": [0]},
            {"The Sanctuary of Oblivion": [0], "Sanctuary": [0], "Oblivion": [0]}
        )
        mock_extract.return_value = ["망각의성채"]  # 띄어쓰기 없음

        text = "망각의성채로 돌아갔다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=80, glossary_path="")

        # 퍼지 매칭으로 찾아야 함
        assert len(result) >= 1
        assert ("망각의 성채", "The Sanctuary of Oblivion") in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_short_term_no_fuzzy(self, mock_extract, mock_entries, mock_index):
        """짧은 용어(3자 미만)는 퍼지 매칭 미적용"""
        mock_entries.return_value = (("루미", "Lumi"),)
        mock_index.return_value = ({"루미": [0]}, {"Lumi": [0]})
        mock_extract.return_value = ["루비"]  # 2글자, 퍼지 미적용

        text = "루비가 다가왔다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=80, glossary_path="")

        # 정확히 일치하지 않고, 퍼지도 안 되므로 빈 결과
        assert len(result) == 0

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_fuzzy_threshold_high(self, mock_extract, mock_entries, mock_index):
        """높은 임계값에서 퍼지 매칭 실패"""
        mock_entries.return_value = (("아리엘라", "Ariella"),)
        mock_index.return_value = ({"아리엘라": [0]}, {"Ariella": [0]})
        mock_extract.return_value = ["아리엘나"]

        text = "아리엘나가 말했다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=95, glossary_path="")

        # 95% 이상 유사해야 하는데 "아리엘나"는 그 정도로 유사하지 않음
        assert ("아리엘라", "Ariella") not in result

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_exact_match_priority(self, mock_extract, mock_entries, mock_index):
        """정확한 매칭이 있으면 퍼지 매칭 중복 안 함"""
        mock_entries.return_value = (("펜릭스", "Fenrix"),)
        mock_index.return_value = ({"펜릭스": [0]}, {"Fenrix": [0]})
        mock_extract.return_value = ["펜릭스"]

        text = "펜릭스가 말했다."
        result = find_relevant_terms(text, "ko", glossary_path="")

        # 정확한 매칭 1개만
        assert len(result) == 1
        assert ("펜릭스", "Fenrix") in result


class TestFindRelevantTermsV2:
    """find_relevant_terms_v2 디버그 정보 테스트"""

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_returns_glossary_match_result(self, mock_extract, mock_entries, mock_index):
        """GlossaryMatchResult 반환 확인"""
        mock_entries.return_value = (("펜릭스", "Fenrix"),)
        mock_index.return_value = ({"펜릭스": [0]}, {"Fenrix": [0]})
        mock_extract.return_value = ["펜릭스"]

        result = find_relevant_terms_v2("펜릭스가 말했다.", "ko", glossary_path="")

        assert isinstance(result, GlossaryMatchResult)
        assert result.matched_terms == [("펜릭스", "Fenrix")]
        assert result.extracted_words == ["펜릭스"]
        assert "exact_matches" in result.debug_info

    @patch("seosoyoung.slackbot.plugins.translate.glossary._build_word_index")
    @patch("seosoyoung.slackbot.plugins.translate.glossary.get_glossary_entries")
    @patch("seosoyoung.slackbot.plugins.translate.glossary._extract_korean_words")
    def test_debug_info_contains_match_types(self, mock_extract, mock_entries, mock_index):
        """디버그 정보에 매칭 유형 포함 확인"""
        mock_entries.return_value = (("펜릭스", "Fenrix"),)
        mock_index.return_value = ({"펜릭스": [0]}, {"Fenrix": [0]})
        mock_extract.return_value = ["펜릭스"]

        result = find_relevant_terms_v2("펜릭스가 말했다.", "ko", glossary_path="")

        debug = result.debug_info
        assert "exact_matches" in debug
        assert "substring_matches" in debug
        assert "fuzzy_matches" in debug
        assert "total_matched" in debug


class TestClearCache:
    """캐시 초기화 테스트"""

    def test_clear_cache_runs(self):
        """캐시 초기화 실행 확인"""
        # 에러 없이 실행되면 성공
        clear_cache()
