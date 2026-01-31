# seosoyoung/config.py

> 경로: `seosoyoung/config.py`

## 개요

설정 관리

## 클래스

### `Config`
- 위치: 줄 18

#### 메서드

- `get_log_path()` (줄 26): 
- `get_session_path()` (줄 30): 
- `get_glossary_path()` (줄 90): 
- `get_narrative_path()` (줄 95): 대사 데이터 경로 (eb_narrative/narrative)
- `get_search_index_path()` (줄 100): 검색 인덱스 경로 (internal/index/dialogues)
- `get_web_cache_path()` (줄 105): 웹 콘텐츠 캐시 경로 (.local/cache/web)

## 함수

### `_get_path(env_var, default_subdir)`
- 위치: 줄 10
- 설명: 환경변수가 없으면 현재 경로 하위 폴더 반환
