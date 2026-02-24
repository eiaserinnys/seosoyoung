# search/embedding_cache.py

> 경로: `seosoyoung/slackbot/search/embedding_cache.py`

## 개요

OpenAI 임베딩 캐시.

텍스트 → 임베딩 벡터 변환 시 SHA256 해시 기반 로컬 캐시를 사용하여
중복 API 호출을 방지한다.

## 클래스

### `EmbeddingCache`
- 위치: 줄 14
- 설명: OpenAI text-embedding-3-small 임베딩 + 로컬 JSON 캐시.

#### 메서드

- `__init__(self, cache_path, api_key, model, batch_size)` (줄 17): 
- `_load(self)` (줄 31): 캐시 파일 로드.
- `save(self)` (줄 37): 캐시 파일 저장.
- `_hash_text(text)` (줄 44): 텍스트의 SHA256 해시.
- `get_embeddings(self, texts)` (줄 48): 텍스트 리스트에 대한 임베딩 벡터 반환.
- `_call_api_batched(self, texts)` (줄 86): 배치 단위로 OpenAI API 호출.
- `get_stats(self)` (줄 100): 캐시 통계.
