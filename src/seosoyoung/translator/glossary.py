"""용어집 로더 모듈

번역 시 고유명사 일관성을 위해 glossary.yaml을 로드하고 파싱합니다.
"""

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from seosoyoung.config import Config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_glossary_raw() -> dict:
    """glossary.yaml 파일을 로드 (캐싱)

    Returns:
        파싱된 YAML 딕셔너리
    """
    glossary_path = Path(Config.get_glossary_path())

    if not glossary_path.exists():
        logger.warning(f"용어집 파일을 찾을 수 없습니다: {glossary_path}")
        return {}

    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"용어집 로드 실패: {e}")
        return {}


def _extract_name_pair(item: dict) -> tuple[str, str] | None:
    """아이템에서 한국어-영어 이름 쌍 추출

    Args:
        item: glossary 항목 (name_kr, name_en 포함)

    Returns:
        (한국어명, 영어명) 튜플 또는 None
    """
    name_kr = item.get("name_kr", {})
    name_en = item.get("name_en", {})

    # name_kr, name_en 내부의 kr/en 키에서 실제 이름 추출
    kr_name = name_kr.get("kr") if isinstance(name_kr, dict) else name_kr
    en_name = name_en.get("en") if isinstance(name_en, dict) else name_en

    if kr_name and en_name:
        return (str(kr_name), str(en_name))
    return None


def _extract_short_names(full_name: str, lang: str = "auto") -> list[str]:
    """전체 이름에서 짧은 이름들을 추출

    예시:
    - "불사의 악마 사냥꾼, 펜릭스 헤이븐" -> ["불사의 악마 사냥꾼", "펜릭스 헤이븐", "펜릭스"]
    - "(눈 먼 정의의 천사) 칼리엘" -> ["칼리엘"]
    - "Fenrix Haven, the Immortal Demon Hunter" -> ["Fenrix Haven", "the Immortal Demon Hunter", "Fenrix"]
    - "Kaliel (Angel of Blind Justice)" -> ["Kaliel"]

    Args:
        full_name: 전체 이름 문자열
        lang: 언어 힌트 ("kr", "en", "auto")

    Returns:
        추출된 짧은 이름 리스트
    """
    import re

    short_names = []

    # 쉼표로 분리
    if "," in full_name:
        parts = [p.strip() for p in full_name.split(",")]
        short_names.extend(parts)

    # 괄호 제거 후 핵심 이름 추출
    # "(이명) 이름" 또는 "이름 (이명)" 패턴
    # 한국어: (눈 먼 정의의 천사) 칼리엘 -> 칼리엘
    # 영어: Kaliel (Angel of Blind Justice) -> Kaliel
    name_without_paren = re.sub(r"\([^)]*\)", "", full_name).strip()
    if name_without_paren and name_without_paren != full_name:
        # 쉼표로 다시 분리
        if "," in name_without_paren:
            parts = [p.strip() for p in name_without_paren.split(",") if p.strip()]
            short_names.extend(parts)
        elif name_without_paren.strip():
            short_names.append(name_without_paren.strip())

    # "이름 성" 패턴에서 "이름"만 추출 (영어)
    # "펜릭스 헤이븐" -> "펜릭스", "Fenrix Haven" -> "Fenrix"
    for name in list(short_names):  # 복사본으로 순회
        words = name.split()
        if len(words) == 2:
            # 첫 번째 단어만 추출 (이름)
            first_word = words[0]
            if len(first_word) >= 2:  # 너무 짧은 것 제외
                short_names.append(first_word)

    # 중복 제거 및 원본과 동일한 것 제외
    result = []
    seen = set()
    for name in short_names:
        if name and name != full_name and name not in seen:
            seen.add(name)
            result.append(name)

    return result


@lru_cache(maxsize=1)
def get_term_mappings() -> tuple[dict[str, str], dict[str, str]]:
    """용어 매핑 딕셔너리 생성 (캐싱)

    Returns:
        (한→영 매핑, 영→한 매핑) 튜플
    """
    raw_data = _load_glossary_raw()
    kr_to_en: dict[str, str] = {}
    en_to_kr: dict[str, str] = {}

    # items 배열을 가진 카테고리들 처리
    categories_with_items = [
        "main_characters", "ariella_variants", "bosses", "boss_human_era",
        "blessing_angels", "npcs", "golems", "system_characters",
        "main_places", "seal_structure", "concepts"
    ]

    for category in categories_with_items:
        category_data = raw_data.get(category, {})
        items = category_data.get("items", [])

        for item in items:
            pair = _extract_name_pair(item)
            if pair:
                kr_name, en_name = pair
                kr_to_en[kr_name] = en_name
                en_to_kr[en_name] = kr_name

                # 짧은 이름들 추출 및 등록
                short_kr_names = _extract_short_names(kr_name)
                short_en_names = _extract_short_names(en_name)

                # 짧은 한국어 이름 -> 대응하는 짧은 영어 이름 (또는 전체 영어 이름)
                for i, short_kr in enumerate(short_kr_names):
                    # 대응하는 짧은 영어 이름이 있으면 사용, 없으면 첫 번째 짧은 영어 이름 사용
                    if i < len(short_en_names):
                        target_en = short_en_names[i]
                    elif short_en_names:
                        target_en = short_en_names[0]
                    else:
                        target_en = en_name
                    kr_to_en[short_kr] = target_en

                # 짧은 영어 이름 -> 대응하는 짧은 한국어 이름
                for i, short_en in enumerate(short_en_names):
                    if i < len(short_kr_names):
                        target_kr = short_kr_names[i]
                    elif short_kr_names:
                        target_kr = short_kr_names[0]
                    else:
                        target_kr = kr_name
                    en_to_kr[short_en] = target_kr

    logger.debug(f"용어집 로드 완료: {len(kr_to_en)}개 한→영, {len(en_to_kr)}개 영→한")
    return kr_to_en, en_to_kr


def clear_cache() -> None:
    """캐시 초기화 (테스트 또는 용어집 갱신 시 사용)"""
    _load_glossary_raw.cache_clear()
    get_term_mappings.cache_clear()


def find_relevant_terms(
    text: str,
    source_lang: str,
    fuzzy_threshold: int = 80
) -> list[tuple[str, str]]:
    """텍스트에서 관련 용어 추출

    부분 문자열 매칭과 퍼지 매칭을 결합하여 관련 용어를 찾습니다.

    Args:
        text: 검색할 텍스트
        source_lang: 원본 언어 ("ko" 또는 "en")
        fuzzy_threshold: 퍼지 매칭 임계값 (기본 80)

    Returns:
        [(원본 용어, 번역된 용어), ...] 리스트
    """
    kr_to_en, en_to_kr = get_term_mappings()

    # 원본 언어에 따라 매핑 선택
    if source_lang == "ko":
        source_terms = kr_to_en
    else:
        source_terms = en_to_kr

    matched: list[tuple[str, str]] = []
    matched_sources: set[str] = set()

    # 1차: 부분 문자열 매칭 (정확한 포함)
    for source_term, target_term in source_terms.items():
        if source_term in text and source_term not in matched_sources:
            matched.append((source_term, target_term))
            matched_sources.add(source_term)

    # 2차: 퍼지 매칭 (rapidfuzz 사용)
    try:
        from rapidfuzz import fuzz

        for source_term, target_term in source_terms.items():
            if source_term in matched_sources:
                continue

            # 긴 용어(4자 이상)에 대해서만 퍼지 매칭 적용
            if len(source_term) >= 4:
                ratio = fuzz.partial_ratio(source_term, text)
                if ratio >= fuzzy_threshold:
                    matched.append((source_term, target_term))
                    matched_sources.add(source_term)
    except ImportError:
        # rapidfuzz가 없으면 부분 문자열 매칭만 사용
        logger.debug("rapidfuzz 미설치, 부분 문자열 매칭만 사용")

    logger.debug(f"용어 매칭 결과: {len(matched)}개 - {matched[:5]}...")
    return matched
