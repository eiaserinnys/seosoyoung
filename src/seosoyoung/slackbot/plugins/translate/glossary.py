"""용어집 로더 모듈

번역 시 고유명사 일관성을 위해 glossary.yaml을 로드하고 파싱합니다.
kiwipiepy를 활용하여 한국어 형태소 분석 기반 용어 매칭을 수행합니다.

이 모듈은 Config에 의존하지 않습니다.
glossary_path는 호출 시 명시적 파라미터로 전달받습니다.
"""

import logging
import re
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass, field

import yaml

# 영어 불용어 (관사, 전치사, 접속사 등) - 개별 매칭에서 제외
ENGLISH_STOPWORDS = frozenset({
    # 관사
    "a", "an", "the",
    # 전치사
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "as",
    "into", "onto", "upon", "about", "above", "below", "between", "among",
    "through", "during", "before", "after", "over", "under", "around",
    # 접속사
    "and", "or", "but", "nor", "yet", "so",
    # 대명사
    "it", "its", "this", "that", "these", "those",
    # 기타 기능어
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "must", "can",
})

logger = logging.getLogger(__name__)

# kiwipiepy 싱글톤 인스턴스
_kiwi = None
_kiwi_initialized = False

# 캐시: glossary_path -> raw data
_glossary_cache: dict[str, dict] = {}
_entries_cache: dict[str, tuple[tuple[str, str], ...]] = {}
_word_index_cache: dict[str, tuple[dict, dict]] = {}


@dataclass
class GlossaryMatchResult:
    """용어 매칭 결과"""
    matched_terms: list[tuple[str, str]]  # [(원본, 번역), ...]
    extracted_words: list[str] = field(default_factory=list)  # 추출된 단어들
    debug_info: dict = field(default_factory=dict)  # 디버그 정보


def _load_glossary_raw(glossary_path: str) -> dict:
    """glossary.yaml 파일을 로드 (캐싱)

    Args:
        glossary_path: 용어집 파일 경로

    Returns:
        파싱된 YAML 딕셔너리
    """
    if glossary_path in _glossary_cache:
        return _glossary_cache[glossary_path]

    path = Path(glossary_path)

    if not path.exists():
        logger.warning(f"용어집 파일을 찾을 수 없습니다: {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _glossary_cache[glossary_path] = data
        return data
    except Exception as e:
        logger.error(f"용어집 로드 실패: {e}")
        return {}


def _extract_name_pair(item: dict) -> tuple[str, str] | None:
    """아이템에서 한국어-영어 이름 쌍 추출

    glossary.yaml 구조: item.name.kr / item.name.en

    Args:
        item: glossary 항목 (name: {kr, en} 포함)

    Returns:
        (한국어명, 영어명) 튜플 또는 None
    """
    name = item.get("name", {})
    if not isinstance(name, dict):
        return None

    kr_name = name.get("kr")
    en_name = name.get("en")

    if kr_name and en_name:
        return (str(kr_name), str(en_name))
    return None


def _extract_short_names(full_name: str) -> list[str]:
    """전체 이름에서 짧은 이름들을 추출 (사용자 사전 등록용)

    Args:
        full_name: 전체 이름 문자열

    Returns:
        추출된 짧은 이름 리스트 (전체 이름 포함)
    """
    names = [full_name]

    # 쉼표로 분리
    if "," in full_name:
        parts = [p.strip() for p in full_name.split(",")]
        names.extend(parts)

    # 괄호 제거 후 핵심 이름 추출
    name_without_paren = re.sub(r"\([^)]*\)", "", full_name).strip()
    if name_without_paren and name_without_paren != full_name:
        if "," in name_without_paren:
            parts = [p.strip() for p in name_without_paren.split(",") if p.strip()]
            names.extend(parts)
        elif name_without_paren.strip():
            names.append(name_without_paren.strip())

    # "이름 성" 패턴에서 첫 단어만 추출
    for name in list(names):
        words = name.split()
        if len(words) == 2 and len(words[0]) >= 2:
            names.append(words[0])

    # 중복 제거
    seen = set()
    result = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            result.append(name)

    return result


def get_glossary_entries(glossary_path: str) -> tuple[tuple[str, str], ...]:
    """용어집 항목들을 (한국어, 영어) 쌍으로 반환 (캐싱)

    Args:
        glossary_path: 용어집 파일 경로

    Returns:
        ((kr_name, en_name), ...) 튜플
    """
    if glossary_path in _entries_cache:
        return _entries_cache[glossary_path]

    raw_data = _load_glossary_raw(glossary_path)
    entries = []

    categories_with_items = [
        "main_characters", "ariella_variants", "bosses", "sub_bosses",
        "boss_human_era", "blessing_angels", "blessings", "npcs", "golems",
        "system_characters", "main_places", "sanctuary_places",
        "seal_structure", "concepts", "items_resources", "terminology",
    ]

    for category in categories_with_items:
        category_data = raw_data.get(category, {})
        items = category_data.get("items", [])

        for item in items:
            pair = _extract_name_pair(item)
            if pair:
                entries.append(pair)

    logger.debug(f"용어집 항목 {len(entries)}개 로드")
    result = tuple(entries)
    _entries_cache[glossary_path] = result
    return result


def _get_kiwi(glossary_path: str):
    """Kiwi 인스턴스 반환 (싱글톤, 사용자 사전 포함)"""
    global _kiwi, _kiwi_initialized

    if _kiwi_initialized:
        return _kiwi

    try:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()

        # 용어집에서 한국어 고유명사 추출하여 사용자 사전에 등록
        entries = get_glossary_entries(glossary_path)
        registered = set()

        for kr_name, _ in entries:
            # 전체 이름과 짧은 이름 모두 등록
            for name in _extract_short_names(kr_name):
                if len(name) >= 2 and name not in registered:
                    try:
                        _kiwi.add_user_word(name, 'NNP')
                        registered.add(name)
                    except Exception:
                        pass  # 이미 등록된 경우 무시

        logger.info(f"kiwipiepy 사용자 사전에 {len(registered)}개 한국어 고유명사 등록")
        _kiwi_initialized = True

    except ImportError:
        logger.warning("kiwipiepy 미설치, 단순 공백 분리 사용")
        _kiwi = None
        _kiwi_initialized = True

    return _kiwi


def _extract_korean_words(text: str, glossary_path: str) -> list[str]:
    """한국어 텍스트에서 명사 추출 (kiwipiepy 사용)

    Args:
        text: 한국어 텍스트
        glossary_path: 용어집 파일 경로

    Returns:
        추출된 명사 리스트 (2글자 이상)
    """
    kiwi = _get_kiwi(glossary_path)

    if kiwi is None:
        # kiwipiepy가 없으면 단순 공백 분리
        words = text.split()
        return [w for w in words if len(w) >= 2]

    tokens = kiwi.tokenize(text)
    nouns = []

    for token in tokens:
        # NNG: 일반명사, NNP: 고유명사, NNB: 의존명사
        if token.tag in ('NNG', 'NNP') and len(token.form) >= 2:
            nouns.append(token.form)

    return nouns


def _extract_english_words(text: str) -> list[str]:
    """영어 텍스트에서 단어 추출

    Args:
        text: 영어 텍스트

    Returns:
        추출된 단어 리스트 (3글자 이상, 불용어 제외)
    """
    words = re.findall(r'[A-Za-z]+', text)
    return [
        w for w in words
        if len(w) >= 3 and w.lower() not in ENGLISH_STOPWORDS
    ]


def _build_word_index(glossary_path: str) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """용어집 역색인 구축 (단어 → 항목 인덱스)

    Args:
        glossary_path: 용어집 파일 경로

    Returns:
        (한국어 역색인, 영어 역색인)
    """
    if glossary_path in _word_index_cache:
        return _word_index_cache[glossary_path]

    entries = get_glossary_entries(glossary_path)
    kr_index: dict[str, list[int]] = {}
    en_index: dict[str, list[int]] = {}

    for idx, (kr_name, en_name) in enumerate(entries):
        # 한국어: 짧은 이름들로 역색인
        for name in _extract_short_names(kr_name):
            if len(name) >= 2:
                kr_index.setdefault(name, []).append(idx)

        # 영어: 짧은 이름들로 역색인
        for name in _extract_short_names(en_name):
            if len(name) >= 3:
                en_index.setdefault(name, []).append(idx)

    logger.debug(f"역색인 구축: 한국어 {len(kr_index)}개, 영어 {len(en_index)}개")
    result = (kr_index, en_index)
    _word_index_cache[glossary_path] = result
    return result


def find_relevant_terms(
    text: str,
    source_lang: str,
    fuzzy_threshold: int = 80,
    *,
    glossary_path: str,
) -> list[tuple[str, str]]:
    """텍스트에서 관련 용어 추출 (하위 호환성 유지)

    Args:
        text: 검색할 텍스트
        source_lang: 원본 언어 ("ko" 또는 "en")
        fuzzy_threshold: 퍼지 매칭 임계값 (기본 80)
        glossary_path: 용어집 파일 경로

    Returns:
        [(원본 용어, 번역된 용어), ...] 리스트
    """
    result = find_relevant_terms_v2(text, source_lang, fuzzy_threshold, glossary_path=glossary_path)
    return result.matched_terms


def find_relevant_terms_v2(
    text: str,
    source_lang: str,
    fuzzy_threshold: int = 80,
    *,
    glossary_path: str,
) -> GlossaryMatchResult:
    """텍스트에서 관련 용어 추출 (개선된 버전, 디버그 정보 포함)

    알고리즘:
    1. 텍스트를 형태소 분석하여 명사 추출 (한국어) 또는 단어 분리 (영어)
    2. 추출된 단어가 용어집 항목에 포함되는지 검색
    3. 퍼지 매칭으로 유사 용어 추가 검색

    Args:
        text: 검색할 텍스트
        source_lang: 원본 언어 ("ko" 또는 "en")
        fuzzy_threshold: 퍼지 매칭 임계값 (기본 80)
        glossary_path: 용어집 파일 경로

    Returns:
        GlossaryMatchResult (매칭 결과, 추출된 단어, 디버그 정보)
    """
    entries = get_glossary_entries(glossary_path)
    kr_index, en_index = _build_word_index(glossary_path)

    # 언어별 단어 추출
    if source_lang == "ko":
        words = _extract_korean_words(text, glossary_path)
        word_index = kr_index
    else:
        words = _extract_english_words(text)
        word_index = en_index

    matched: list[tuple[str, str]] = []
    matched_indices: set[int] = set()
    exact_matches: list[str] = []
    substring_matches: list[str] = []
    fuzzy_matches: list[str] = []

    # 1단계: 역색인을 통한 정확한 단어 매칭
    for word in words:
        if word in word_index:
            for idx in word_index[word]:
                if idx not in matched_indices:
                    kr_name, en_name = entries[idx]
                    source_name = kr_name if source_lang == "ko" else en_name
                    target_name = en_name if source_lang == "ko" else kr_name
                    matched.append((source_name, target_name))
                    matched_indices.add(idx)
                    exact_matches.append(f"{word} → {source_name}")

    # 2단계: 단어가 용어집 항목에 부분 포함되는지 검색
    for word in words:
        if len(word) < 2:
            continue

        for idx, (kr_name, en_name) in enumerate(entries):
            if idx in matched_indices:
                continue

            source_name = kr_name if source_lang == "ko" else en_name
            target_name = en_name if source_lang == "ko" else kr_name

            if word in source_name:
                matched.append((source_name, target_name))
                matched_indices.add(idx)
                substring_matches.append(f"{word} ⊂ {source_name}")

    # 3단계: 퍼지 매칭
    try:
        from rapidfuzz import fuzz

        for word in words:
            if len(word) < 3:  # 퍼지 매칭은 3글자 이상만
                continue

            for idx, (kr_name, en_name) in enumerate(entries):
                if idx in matched_indices:
                    continue

                source_name = kr_name if source_lang == "ko" else en_name
                target_name = en_name if source_lang == "ko" else kr_name

                # 짧은 이름들과 퍼지 매칭
                for short_name in _extract_short_names(source_name):
                    if len(short_name) < 3:
                        continue

                    ratio = fuzz.ratio(word, short_name)
                    if ratio >= fuzzy_threshold:
                        matched.append((source_name, target_name))
                        matched_indices.add(idx)
                        fuzzy_matches.append(f"{word} ≈ {short_name} ({ratio}%)")
                        break

    except ImportError:
        logger.debug("rapidfuzz 미설치, 퍼지 매칭 건너뜀")

    debug_info = {
        "extracted_words": words,
        "exact_matches": exact_matches,
        "substring_matches": substring_matches,
        "fuzzy_matches": fuzzy_matches,
        "total_matched": len(matched),
    }

    logger.debug(f"용어 매칭: {len(words)}개 단어 → {len(matched)}개 매칭")

    return GlossaryMatchResult(
        matched_terms=matched,
        extracted_words=words,
        debug_info=debug_info
    )


def clear_cache() -> None:
    """캐시 초기화 (테스트 또는 용어집 갱신 시 사용)"""
    global _kiwi, _kiwi_initialized
    _glossary_cache.clear()
    _entries_cache.clear()
    _word_index_cache.clear()
    _kiwi = None
    _kiwi_initialized = False
