# slackbot/config.py

> 경로: `seosoyoung/slackbot/config.py`

## 개요

설정 관리

카테고리별로 구분된 설정을 관리합니다.
- 경로 설정: get_*() 메서드 (cwd 기준 계산 필요)
- 그 외 설정: @dataclass 하위 그룹 (모듈 로드 시 평가)

## 클래스

### `ConfigurationError` (Exception)
- 위치: 줄 18
- 설명: 설정 오류 예외

필수 환경변수 누락 등 설정 관련 오류 시 발생합니다.

#### 메서드

- `__init__(self, missing_vars)` (줄 24): 

### `SlackConfig`
- 위치: 줄 60
- 설명: Slack 연결 설정

### `AuthConfig`
- 위치: 줄 70
- 설명: 권한 설정

### `TrelloConfig`
- 위치: 줄 90
- 설명: Trello 설정

### `TranslateConfig`
- 위치: 줄 111
- 설명: 번역 설정

### `GeminiConfig`
- 위치: 줄 132
- 설명: Gemini 설정 (이미지 생성)

### `OMConfig`
- 위치: 줄 140
- 설명: Observational Memory 설정

### `ChannelObserverConfig`
- 위치: 줄 166
- 설명: Channel Observer 설정

### `ClaudeConfig`
- 위치: 줄 219
- 설명: Claude 실행 모드 설정

remote 모드에서 Soulstream 서버(독립 soul-server)에 연결합니다.

### `EmojiConfig`
- 위치: 줄 232
- 설명: 이모지 설정

### `Config`
- 위치: 줄 260
- 설명: 애플리케이션 설정

설정 접근 방식:
- 경로 관련: get_*() 메서드 (런타임에 cwd 기준 계산)
- 그 외: 하위 설정 그룹 (모듈 로드 시 평가)

#### 메서드

- `get_log_path()` (줄 284): 로그 경로
- `get_session_path()` (줄 289): 세션 경로
- `get_glossary_path()` (줄 294): 용어집 경로 (번역 시 고유명사 참조)
- `get_narrative_path()` (줄 299): 대사 데이터 경로
- `get_search_index_path()` (줄 304): 검색 인덱스 경로
- `get_web_cache_path()` (줄 309): 웹 콘텐츠 캐시 경로
- `get_memory_path()` (줄 314): 관찰 로그 저장 경로
- `validate(cls)` (줄 322): 필수 환경변수 검증

## 함수

### `_get_path(env_var, default_subdir)`
- 위치: 줄 30
- 설명: 환경변수가 없으면 현재 경로 하위 폴더 반환

### `_parse_bool(value, default)`
- 위치: 줄 38
- 설명: 문자열을 bool로 변환

### `_parse_int(value, default)`
- 위치: 줄 45
- 설명: 문자열을 int로 변환

### `_parse_float(value, default)`
- 위치: 줄 52
- 설명: 문자열을 float로 변환
