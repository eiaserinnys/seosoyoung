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
- `get_glossary_path()` (줄 91): 
- `get_narrative_path()` (줄 96): 대사 데이터 경로 (eb_narrative/narrative)
- `get_search_index_path()` (줄 101): 검색 인덱스 경로 (internal/index/dialogues)
- `get_web_cache_path()` (줄 106): 웹 콘텐츠 캐시 경로 (.local/cache/web)
- `get_recall_enabled()` (줄 112): Recall 활성화 여부
- `get_recall_model()` (줄 117): Recall에 사용할 모델
- `get_recall_threshold()` (줄 122): Recall 적합도 임계값 (1-10)
- `get_recall_timeout()` (줄 127): Recall 타임아웃 (초)

## 함수

### `_get_path(env_var, default_subdir)`
- 위치: 줄 10
- 설명: 환경변수가 없으면 현재 경로 하위 폴더 반환
