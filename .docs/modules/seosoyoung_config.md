# seosoyoung/config.py

> 경로: `seosoyoung/config.py`

## 개요

설정 관리

카테고리별로 구분된 설정을 관리합니다.
- 경로 설정: get_*() 메서드 (cwd 기준 계산 필요)
- 그 외 설정: 클래스 변수 (모듈 로드 시 평가)

## 클래스

### `ConfigurationError` (Exception)
- 위치: 줄 17
- 설명: 설정 오류 예외

필수 환경변수 누락 등 설정 관련 오류 시 발생합니다.

#### 메서드

- `__init__(self, missing_vars)` (줄 23): 

### `Config`
- 위치: 줄 58
- 설명: 애플리케이션 설정

설정 접근 방식:
- 경로 관련: get_*() 메서드 (런타임에 cwd 기준 계산)
- 그 외: 클래스 변수 (모듈 로드 시 평가)

#### 메서드

- `get_log_path()` (줄 176): 로그 경로
- `get_session_path()` (줄 181): 세션 경로
- `get_glossary_path()` (줄 186): 용어집 경로 (번역 시 고유명사 참조)
- `get_narrative_path()` (줄 191): 대사 데이터 경로
- `get_search_index_path()` (줄 196): 검색 인덱스 경로
- `get_web_cache_path()` (줄 201): 웹 콘텐츠 캐시 경로
- `get_memory_path()` (줄 206): 관찰 로그 저장 경로
- `validate(cls)` (줄 216): 필수 환경변수 검증

## 함수

### `_get_path(env_var, default_subdir)`
- 위치: 줄 29
- 설명: 환경변수가 없으면 현재 경로 하위 폴더 반환

### `_parse_bool(value, default)`
- 위치: 줄 37
- 설명: 문자열을 bool로 변환

### `_parse_int(value, default)`
- 위치: 줄 44
- 설명: 문자열을 int로 변환

### `_parse_float(value, default)`
- 위치: 줄 51
- 설명: 문자열을 float로 변환
