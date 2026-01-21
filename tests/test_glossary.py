"""용어집 모듈 테스트"""

import pytest
from unittest.mock import patch, mock_open

from seosoyoung.translator.glossary import (
    _extract_name_pair,
    get_term_mappings,
    find_relevant_terms,
    clear_cache,
)


# 테스트용 샘플 YAML 데이터
SAMPLE_GLOSSARY_YAML = """
id: glossary

main_characters:
  items:
    - name_kr:
        kr: 펜릭스 헤이븐
        en: Fenrix Haven
      name_en:
        kr: Fenrix Haven
        en: Fenrix Haven
    - name_kr:
        kr: 성채의 수호자, 아리엘라 애시우드
        en: Ariella Ashwood, the Guardian of the Sanctuary
      name_en:
        kr: Ariella Ashwood, the Guardian of the Sanctuary
        en: Ariella Ashwood, the Guardian of the Sanctuary

main_places:
  items:
    - name_kr:
        kr: 망각의 성채
        en: The Sanctuary of Oblivion
      name_en:
        kr: The Sanctuary of Oblivion
        en: The Sanctuary of Oblivion
"""


class TestExtractNamePair:
    """이름 쌍 추출 테스트"""

    def test_extract_valid_pair(self):
        """유효한 이름 쌍 추출"""
        item = {
            "name_kr": {"kr": "펜릭스", "en": "Fenrix"},
            "name_en": {"kr": "Fenrix", "en": "Fenrix"},
        }
        result = _extract_name_pair(item)
        assert result == ("펜릭스", "Fenrix")

    def test_extract_missing_name_kr(self):
        """name_kr 누락"""
        item = {"name_en": {"kr": "Fenrix", "en": "Fenrix"}}
        result = _extract_name_pair(item)
        assert result is None

    def test_extract_empty_item(self):
        """빈 항목"""
        result = _extract_name_pair({})
        assert result is None


class TestGetTermMappings:
    """용어 매핑 테스트"""

    @patch("seosoyoung.translator.glossary.Config")
    @patch("builtins.open", mock_open(read_data=SAMPLE_GLOSSARY_YAML))
    @patch("seosoyoung.translator.glossary.Path")
    def test_get_term_mappings(self, mock_path, mock_config):
        """용어 매핑 생성"""
        clear_cache()

        mock_config.get_glossary_path.return_value = "test/glossary.yaml"
        mock_path_instance = mock_path.return_value
        mock_path_instance.exists.return_value = True

        kr_to_en, en_to_kr = get_term_mappings()

        # 기본 매핑 확인
        assert "펜릭스 헤이븐" in kr_to_en
        assert kr_to_en["펜릭스 헤이븐"] == "Fenrix Haven"

        # 역방향 매핑 확인
        assert "Fenrix Haven" in en_to_kr
        assert en_to_kr["Fenrix Haven"] == "펜릭스 헤이븐"

        # 장소 매핑 확인
        assert "망각의 성채" in kr_to_en
        assert kr_to_en["망각의 성채"] == "The Sanctuary of Oblivion"

    @patch("seosoyoung.translator.glossary.Config")
    @patch("seosoyoung.translator.glossary.Path")
    def test_get_term_mappings_file_not_found(self, mock_path, mock_config):
        """파일 없을 때 빈 매핑 반환"""
        clear_cache()

        mock_config.get_glossary_path.return_value = "nonexistent.yaml"
        mock_path_instance = mock_path.return_value
        mock_path_instance.exists.return_value = False

        kr_to_en, en_to_kr = get_term_mappings()

        assert kr_to_en == {}
        assert en_to_kr == {}


class TestFindRelevantTerms:
    """관련 용어 찾기 테스트"""

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_find_korean_terms(self, mock_mappings):
        """한국어 텍스트에서 용어 찾기"""
        mock_mappings.return_value = (
            {"펜릭스": "Fenrix", "아리엘라": "Ariella"},
            {"Fenrix": "펜릭스", "Ariella": "아리엘라"},
        )

        text = "펜릭스가 아리엘라에게 말했다."
        result = find_relevant_terms(text, "ko")

        assert len(result) == 2
        assert ("펜릭스", "Fenrix") in result
        assert ("아리엘라", "Ariella") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_find_english_terms(self, mock_mappings):
        """영어 텍스트에서 용어 찾기"""
        mock_mappings.return_value = (
            {"펜릭스": "Fenrix", "아리엘라": "Ariella"},
            {"Fenrix": "펜릭스", "Ariella": "아리엘라"},
        )

        text = "Fenrix spoke to Ariella."
        result = find_relevant_terms(text, "en")

        assert len(result) == 2
        assert ("Fenrix", "펜릭스") in result
        assert ("Ariella", "아리엘라") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_find_no_matching_terms(self, mock_mappings):
        """매칭되는 용어 없음"""
        mock_mappings.return_value = (
            {"펜릭스": "Fenrix"},
            {"Fenrix": "펜릭스"},
        )

        text = "Hello world"
        result = find_relevant_terms(text, "en")

        assert len(result) == 0

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_no_duplicate_matches(self, mock_mappings):
        """중복 매칭 방지"""
        mock_mappings.return_value = (
            {"펜릭스": "Fenrix"},
            {"Fenrix": "펜릭스"},
        )

        text = "펜릭스가 펜릭스에게 말했다."
        result = find_relevant_terms(text, "ko")

        # 같은 용어는 한 번만 포함
        assert len(result) == 1
        assert ("펜릭스", "Fenrix") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_fuzzy_match_typo(self, mock_mappings):
        """오타가 있는 용어 퍼지 매칭"""
        mock_mappings.return_value = (
            {"아리엘라": "Ariella", "펜릭스 헤이븐": "Fenrix Haven"},
            {"Ariella": "아리엘라", "Fenrix Haven": "펜릭스 헤이븐"},
        )

        # "아리엘라" 대신 "아리엘나" (오타)
        text = "아리엘나가 말했다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=80)

        # 퍼지 매칭으로 유사한 용어 찾아야 함
        assert len(result) >= 1
        assert ("아리엘라", "Ariella") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_fuzzy_match_english_typo(self, mock_mappings):
        """영어 오타 퍼지 매칭"""
        mock_mappings.return_value = (
            {"아리엘라": "Ariella"},
            {"Ariella": "아리엘라"},
        )

        # "Ariella" 대신 "Ariela" (오타)
        text = "Ariela spoke quietly."
        result = find_relevant_terms(text, "en", fuzzy_threshold=80)

        assert len(result) >= 1
        assert ("Ariella", "아리엘라") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_fuzzy_match_partial_name(self, mock_mappings):
        """부분 이름 퍼지 매칭"""
        mock_mappings.return_value = (
            {"망각의 성채": "The Sanctuary of Oblivion"},
            {"The Sanctuary of Oblivion": "망각의 성채"},
        )

        # "망각의 성채" 대신 "망각의성채" (띄어쓰기 없음)
        text = "망각의성채로 돌아갔다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=80)

        assert len(result) >= 1
        assert ("망각의 성채", "The Sanctuary of Oblivion") in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_short_term_no_fuzzy(self, mock_mappings):
        """짧은 용어(4자 미만)는 퍼지 매칭 미적용"""
        mock_mappings.return_value = (
            {"루미": "Lumi"},
            {"Lumi": "루미"},
        )

        # "루미" 대신 "루비" - 3자라서 퍼지 매칭 안 함
        text = "루비가 다가왔다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=80)

        # 정확히 일치하지 않고, 퍼지도 안 되므로 빈 결과
        assert len(result) == 0

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_fuzzy_threshold_high(self, mock_mappings):
        """높은 임계값에서 퍼지 매칭 실패"""
        mock_mappings.return_value = (
            {"아리엘라": "Ariella"},
            {"Ariella": "아리엘라"},
        )

        # 임계값을 95%로 높이면 오타 매칭 안 됨
        text = "아리엘나가 말했다."
        result = find_relevant_terms(text, "ko", fuzzy_threshold=95)

        # 95% 이상 유사해야 하는데 "아리엘나"는 그 정도로 유사하지 않음
        assert ("아리엘라", "Ariella") not in result

    @patch("seosoyoung.translator.glossary.get_term_mappings")
    def test_exact_match_priority(self, mock_mappings):
        """정확한 매칭이 있으면 퍼지 매칭 중복 안 함"""
        mock_mappings.return_value = (
            {"펜릭스": "Fenrix"},
            {"Fenrix": "펜릭스"},
        )

        # 정확히 "펜릭스"가 있는 경우
        text = "펜릭스가 말했다."
        result = find_relevant_terms(text, "ko")

        # 정확한 매칭 1개만
        assert len(result) == 1
        assert ("펜릭스", "Fenrix") in result


class TestClearCache:
    """캐시 초기화 테스트"""

    def test_clear_cache_runs(self):
        """캐시 초기화 실행 확인"""
        # 에러 없이 실행되면 성공
        clear_cache()
