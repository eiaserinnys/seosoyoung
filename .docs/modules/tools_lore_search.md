# tools/lore_search.py

> 경로: `seosoyoung/mcp/tools/lore_search.py`

## 개요

A-RAG 로어 검색 MCP 도구 — keyword_search, semantic_search, chunk_read.

Phase 1-2에서 구축한 Whoosh 인덱스 + 임베딩 인덱스를 활용하여
계층적 검색 인터페이스를 제공한다.

## 함수

### `_track_chunk(chunk_id)`
- 위치: 줄 31
- 설명: chunk_id를 추적하고, 이미 읽은 청크면 True 반환.

### `_gc_tracker()`
- 위치: 줄 42
- 설명: TTL이 지난 항목 정리.

### `reset_context_tracker()`
- 위치: 줄 50
- 설명: 테스트용: 트래커 초기화.

### `_get_index_base_path()`
- 위치: 줄 59
- 설명: 인덱스 기본 경로.

### `_get_dialogue_searcher()`
- 위치: 줄 64
- 설명: Whoosh 대사 인덱스 searcher (lazy load).

### `_get_lore_searcher()`
- 위치: 줄 74
- 설명: Whoosh 로어 인덱스 (lazy load).

### `_get_embedding_data(prefix)`
- 위치: 줄 84
- 설명: 임베딩 벡터 + 메타데이터 (lazy load).

### `_get_embedding_cache()`
- 위치: 줄 93
- 설명: 임베딩 캐시 (쿼리 임베딩용, lazy load).

### `reset_indices()`
- 위치: 줄 101
- 설명: 테스트용: 인덱스 캐시 초기화.

### `lore_keyword_search(keywords, speaker, source, top_k)`
- 위치: 줄 106
- 설명: 키워드 기반 로어/대사 검색.

Whoosh 인덱스에서 키워드를 검색하여 chunk_id + 매칭 스니펫을 반환한다.

Args:
    keywords: 검색 키워드 리스트
    speaker: 화자 필터 (대사 전용, 예: fx, ar)
    source: 검색 대상 — "dlg" (대사), "lore" (설정), "all" (전체)
    top_k: 최대 결과 수

Returns:
    검색 결과 dict

### `_search_dialogue_whoosh(query_text, speaker, top_k)`
- 위치: 줄 154
- 설명: Whoosh 대사 인덱스 검색.

### `_search_lore_whoosh(query_text, top_k)`
- 위치: 줄 184
- 설명: Whoosh 로어 인덱스 검색.

### `lore_semantic_search(query, speaker, source, top_k)`
- 위치: 줄 210
- 설명: 의미 기반 로어/대사 검색.

쿼리를 임베딩 벡터로 변환 후 코사인 유사도로 검색한다.
A-RAG 방식으로 부모 청크 기준 집계.

Args:
    query: 검색 쿼리 텍스트
    speaker: 화자 필터 (대사 전용)
    source: 검색 대상 — "dlg", "lore", "all"
    top_k: 최대 결과 수

Returns:
    검색 결과 dict

### `lore_chunk_read(chunk_id, include_adjacent)`
- 위치: 줄 300
- 설명: chunk_id로 전체 텍스트를 읽는다.

- dlg 청크 (dlgId): 한/영 전체 텍스트 반환
- lore 청크 (char:fx:basic_info 등): 해당 YAML 섹션 전체 텍스트 반환
- Context Tracker: 이미 읽은 청크는 간략 메시지만 반환 (토큰 절약)

Args:
    chunk_id: 청크 ID (dlgId 또는 lore chunk_id)
    include_adjacent: True면 인접 대사/섹션도 포함

Returns:
    청크 전체 텍스트 dict

### `_read_dialogue_chunk(chunk_id, include_adjacent)`
- 위치: 줄 333
- 설명: dlgId로 대사 전체 텍스트 읽기.

### `_get_adjacent_dialogues(dlg_id, source_file)`
- 위치: 줄 365
- 설명: 같은 dlglist 파일에서 인접 대사를 가져온다.

### `_read_lore_chunk(chunk_id, include_adjacent)`
- 위치: 줄 409
- 설명: lore chunk_id로 원본 YAML 섹션 읽기.

### `_get_adjacent_lore_sections(chunk_id, entry)`
- 위치: 줄 440
- 설명: 같은 엔티티의 인접 섹션을 가져온다.

## 내부 의존성

- `seosoyoung.slackbot.search.embedding_cache.EmbeddingCache`
- `seosoyoung.slackbot.search.embedding_index.cosine_similarity_search`
- `seosoyoung.slackbot.search.embedding_index.load_embedding_index`
