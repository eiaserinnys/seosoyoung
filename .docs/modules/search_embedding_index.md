# search/embedding_index.py

> 경로: `seosoyoung/slackbot/search/embedding_index.py`

## 개요

임베딩 인덱스 빌더 + 코사인 유사도 검색.

A-RAG 방식: 문장 단위 임베딩 생성 → 검색 시 부모 청크(dlgId/chunk_id) 기준 집계.

## 클래스

### `EmbeddingIndexBuilder`
- 위치: 줄 45
- 설명: dlglist 대사와 eb_lore 텍스트를 문장 단위 임베딩 인덱스로 빌드.

#### 메서드

- `__init__(self, narrative_path, lore_path, output_dir, cache_path, api_key)` (줄 48): 
- `build_dialogue_index(self)` (줄 65): dlglist 대사를 문장 분할 → 임베딩 인덱스 생성.
- `build_lore_index(self)` (줄 128): eb_lore 텍스트를 문장 분할 → 임베딩 인덱스 생성.
- `_index_entity(self, yaml_file, source_type, sentences, metadata)` (줄 191): 캐릭터/장소/시놉시스 YAML → 문장 분할.
- `_index_glossary(self, glossary_file, sentences, metadata)` (줄 244): 용어집 YAML → 문장 분할.
- `_embed_sentences(self, sentences)` (줄 302): 문장 리스트 → 임베딩 벡터 (numpy).
- `_save_index(self, vectors, metadata, prefix)` (줄 310): 벡터 + 메타데이터를 파일로 저장.
- `_save_build_info(self, prefix, stats)` (줄 323): 빌드 메타 정보 저장.

## 함수

### `_section_text(section_data)`
- 위치: 줄 20
- 설명: 섹션 dict에서 kr/en 텍스트 추출 (lore_indexer와 동일 로직).

### `_is_content_section(key, value)`
- 위치: 줄 38
- 설명: kr/en 텍스트를 포함하는 콘텐츠 섹션인지.

### `load_embedding_index(index_dir, prefix)`
- 위치: 줄 335
- 설명: 저장된 임베딩 인덱스 로드.

Args:
    index_dir: 인덱스 디렉토리
    prefix: 'dialogue' 또는 'lore'

Returns:
    (vectors, metadata) 튜플

### `cosine_similarity_search(query_vector, vectors, metadata, top_k, aggregate_by_chunk)`
- 위치: 줄 363
- 설명: 코사인 유사도 기반 검색.

Args:
    query_vector: 쿼리 벡터 (1D)
    vectors: 인덱스 벡터 (N x D)
    metadata: 각 벡터의 메타데이터
    top_k: 반환할 최대 결과 수
    aggregate_by_chunk: True면 chunk_id 기준 집계 (A-RAG 방식)

Returns:
    검색 결과 리스트 (score 내림차순)
