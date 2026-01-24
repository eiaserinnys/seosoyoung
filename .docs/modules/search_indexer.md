# search/indexer.py

> 경로: `seosoyoung/search/indexer.py`

## 개요

Whoosh indexer for dialogue data.

## 클래스

### `DialogueIndexer`
- 위치: 줄 14
- 설명: dlglist YAML 파일을 Whoosh 인덱스로 변환.

#### 메서드

- `__init__(self, narrative_path, index_path)` (줄 17): Args:
- `create_index(self, force)` (줄 32): 인덱스 생성 또는 열기.
- `index_all(self, force)` (줄 47): 모든 dlglist 파일 인덱싱.
- `_index_file(self, writer, yaml_file)` (줄 91): 개별 YAML 파일 인덱싱.

## 함수

### `get_default_paths()`
- 위치: 줄 144
- 설명: 기본 경로 반환.

Returns:
    (narrative_path, index_path) 튜플

### `build_index(narrative_path, index_path, force)`
- 위치: 줄 156
- 설명: 인덱스 빌드 CLI 진입점.

Args:
    narrative_path: eb_narrative/narrative 경로 (None이면 기본값)
    index_path: 인덱스 저장 경로 (None이면 기본값)
    force: True면 기존 인덱스 삭제 후 재생성

Returns:
    통계 정보 dict
