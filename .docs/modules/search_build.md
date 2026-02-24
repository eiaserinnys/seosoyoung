# search/build.py

> 경로: `seosoyoung/slackbot/search/build.py`

## 개요

통합 빌드 스크립트 — Whoosh + 임베딩 인덱스를 한 번에 빌드.

Usage:
    python -m seosoyoung.slackbot.search.build                    # 전체 빌드
    python -m seosoyoung.slackbot.search.build --whoosh-only      # Whoosh만
    python -m seosoyoung.slackbot.search.build --embedding-only   # 임베딩만
    python -m seosoyoung.slackbot.search.build --force            # 강제 재빌드

## 함수

### `build_whoosh(narrative_path, lore_path, index_root, force)`
- 위치: 줄 19
- 설명: Whoosh 인덱스 빌드 (대사 + 로어).

narrative_path는 eb_narrative 루트 (예: ./eb_narrative).
DialogueIndexer는 내부적으로 narrative_path/dlglist를 보므로
narrative/dlglist 구조에 맞게 narrative/ 서브디렉토리를 전달한다.

### `build_embeddings(narrative_path, lore_path, index_root, cache_path, api_key)`
- 위치: 줄 55
- 설명: 임베딩 인덱스 빌드 (대사 + 로어).

### `build_all(narrative_path, lore_path, index_root, force, whoosh_only, embedding_only, cache_path, api_key)`
- 위치: 줄 84
- 설명: Whoosh + 임베딩 인덱스 통합 빌드.

Args:
    narrative_path: eb_narrative 경로 (narrative/ 포함)
    lore_path: eb_lore 경로 (content/ 포함)
    index_root: 인덱스 루트 디렉토리
    force: 강제 재빌드
    whoosh_only: Whoosh만 빌드
    embedding_only: 임베딩만 빌드
    cache_path: 임베딩 캐시 경로
    api_key: OpenAI API key

Returns:
    빌드 결과 통계

### `main()`
- 위치: 줄 131
- 설명: CLI 진입점.
