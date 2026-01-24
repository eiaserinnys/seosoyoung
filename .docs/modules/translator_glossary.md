# translator/glossary.py

> 경로: `seosoyoung/translator/glossary.py`

## 개요

용어집 로더 모듈

번역 시 고유명사 일관성을 위해 glossary.yaml을 로드하고 파싱합니다.
kiwipiepy를 활용하여 한국어 형태소 분석 기반 용어 매칭을 수행합니다.

## 클래스

### `GlossaryMatchResult`
- 위치: 줄 43
- 설명: 용어 매칭 결과

## 함수

### `_load_glossary_raw()`
- 위치: 줄 51
- 데코레이터: lru_cache
- 설명: glossary.yaml 파일을 로드 (캐싱)

Returns:
    파싱된 YAML 딕셔너리

### `_extract_name_pair(item)`
- 위치: 줄 71
- 설명: 아이템에서 한국어-영어 이름 쌍 추출

Args:
    item: glossary 항목 (name_kr, name_en 포함)

Returns:
    (한국어명, 영어명) 튜플 또는 None

### `_extract_short_names(full_name)`
- 위치: 줄 92
- 설명: 전체 이름에서 짧은 이름들을 추출 (사용자 사전 등록용)

Args:
    full_name: 전체 이름 문자열

Returns:
    추출된 짧은 이름 리스트 (전체 이름 포함)

### `get_glossary_entries()`
- 위치: 줄 135
- 데코레이터: lru_cache
- 설명: 용어집 항목들을 (한국어, 영어) 쌍으로 반환 (캐싱)

Returns:
    ((kr_name, en_name), ...) 튜플

### `_get_kiwi()`
- 위치: 줄 163
- 설명: Kiwi 인스턴스 반환 (싱글톤, 사용자 사전 포함)

### `_extract_korean_words(text)`
- 위치: 줄 199
- 설명: 한국어 텍스트에서 명사 추출 (kiwipiepy 사용)

Args:
    text: 한국어 텍스트

Returns:
    추출된 명사 리스트 (2글자 이상)

### `_extract_english_words(text)`
- 위치: 줄 226
- 설명: 영어 텍스트에서 단어 추출

Args:
    text: 영어 텍스트

Returns:
    추출된 단어 리스트 (3글자 이상, 불용어 제외)

### `_build_word_index()`
- 위치: 줄 243
- 데코레이터: lru_cache
- 설명: 용어집 역색인 구축 (단어 → 항목 인덱스)

Returns:
    (한국어 역색인, 영어 역색인)

### `find_relevant_terms(text, source_lang, fuzzy_threshold)`
- 위치: 줄 268
- 설명: 텍스트에서 관련 용어 추출 (하위 호환성 유지)

Args:
    text: 검색할 텍스트
    source_lang: 원본 언어 ("ko" 또는 "en")
    fuzzy_threshold: 퍼지 매칭 임계값 (기본 80)

Returns:
    [(원본 용어, 번역된 용어), ...] 리스트

### `find_relevant_terms_v2(text, source_lang, fuzzy_threshold)`
- 위치: 줄 287
- 설명: 텍스트에서 관련 용어 추출 (개선된 버전, 디버그 정보 포함)

알고리즘:
1. 텍스트를 형태소 분석하여 명사 추출 (한국어) 또는 단어 분리 (영어)
2. 추출된 단어가 용어집 항목에 포함되는지 검색
3. 퍼지 매칭으로 유사 용어 추가 검색

Args:
    text: 검색할 텍스트
    source_lang: 원본 언어 ("ko" 또는 "en")
    fuzzy_threshold: 퍼지 매칭 임계값 (기본 80)

Returns:
    GlossaryMatchResult (매칭 결과, 추출된 단어, 디버그 정보)

### `get_term_mappings()`
- 위치: 줄 403
- 데코레이터: lru_cache
- 설명: 용어 매핑 딕셔너리 생성 (하위 호환성 유지)

Returns:
    (한→영 매핑, 영→한 매핑) 튜플

### `clear_cache()`
- 위치: 줄 433
- 설명: 캐시 초기화 (테스트 또는 용어집 갱신 시 사용)

## 내부 의존성

- `seosoyoung.config.Config`
