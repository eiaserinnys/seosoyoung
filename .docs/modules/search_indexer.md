# search/indexer.py

> 경로: `seosoyoung/search/indexer.py`

## 개요

Dialogue indexer — dlglist YAML → Whoosh index.

`.tools/build-dialogue-index/main.py`에서 이전된 인덱서.
DialogueReferenceMap으로 대화 구조 파일에서 dlgId 메타데이터를 수집한 뒤,
DialogueIndexer가 dlglist YAML을 Whoosh 인덱스로 변환한다.

## 클래스

### `DialogueMetadata`
- 위치: 줄 19
- 설명: dlgId에 대한 메타데이터.

### `DialogueReferenceMap`
- 위치: 줄 27
- 설명: 대화 구조 파일을 스캔하여 dlgId → 메타데이터 역참조 맵 생성.

#### 메서드

- `__init__(self, narrative_path)` (줄 30): 
- `build(self)` (줄 34): 모든 구조 파일을 스캔하여 역참조 맵 생성.
- `_scan_revision(self, rev_path, revision)` (줄 45): 리비전 폴더 스캔.
- `_process_structure_file(self, yaml_file, revision)` (줄 53): 개별 구조 파일 처리.
- `_extract_acts_from_path(self, yaml_file, revision)` (줄 99): 파일 경로에서 액트 정보 추출.
- `_collect_dlgids(self, items, label, revision, acts, trigger)` (줄 109): dlgId 항목 수집 및 메타데이터 기록.
- `get(self, dlgId)` (줄 142): dlgId에 대한 메타데이터 조회.
- `get_stats(self)` (줄 146): 역참조 맵 통계.

### `DialogueIndexer`
- 위치: 줄 164
- 설명: dlglist YAML 파일을 Whoosh 인덱스로 변환.

#### 메서드

- `__init__(self, narrative_path, index_path)` (줄 167): 
- `create_index(self, force)` (줄 173): 인덱스 생성 또는 열기.
- `index_all(self, force)` (줄 184): 모든 dlglist 파일 인덱싱.
- `_index_file(self, writer, yaml_file)` (줄 216): 개별 YAML 파일 인덱싱.
