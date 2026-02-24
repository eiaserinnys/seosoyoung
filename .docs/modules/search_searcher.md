# search/searcher.py

> 경로: `seosoyoung/slackbot/search/searcher.py`

## 개요

Whoosh searcher for dialogue data.

## 클래스

### `DialogueSearcher`
- 위치: 줄 14
- 설명: 대사 검색 API.

#### 메서드

- `__init__(self, index_path)` (줄 17): Args:
- `search(self, query_text, speaker, label, revision, act, trigger, fuzzy, highlight, limit)` (줄 32): 대사 검색.
- `search_by_dlgid(self, dlgId)` (줄 161): dlgId로 정확히 검색.
- `get_stats(self)` (줄 188): 인덱스 통계 조회.

## 함수

### `get_default_index_path()`
- 위치: 줄 197
- 설명: 기본 인덱스 경로 반환.

### `format_results(results, format_type)`
- 위치: 줄 202
- 설명: 결과 포맷팅.

Args:
    results: 검색 결과
    format_type: json 또는 brief

### `main()`
- 위치: 줄 222
- 설명: CLI 진입점.
