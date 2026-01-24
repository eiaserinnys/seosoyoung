# search/reference.py

> 경로: `seosoyoung/search/reference.py`

## 개요

대화 구조 파일에서 dlgId → 메타데이터 역참조 맵 생성.

## 클래스

### `DialogueMetadata`
- 위치: 줄 11
- 설명: dlgId에 대한 메타데이터.

### `DialogueReferenceMap`
- 위치: 줄 19
- 설명: 대화 구조 파일을 스캔하여 dlgId → 메타데이터 역참조 맵 생성.

#### 메서드

- `__init__(self, narrative_path)` (줄 22): Args:
- `build(self)` (줄 30): 모든 구조 파일을 스캔하여 역참조 맵 생성.
- `_scan_revision(self, rev_path, revision)` (줄 47): 리비전 폴더 스캔.
- `_process_structure_file(self, yaml_file, revision)` (줄 61): 개별 구조 파일 처리.
- `_extract_acts_from_path(self, yaml_file, revision)` (줄 123): 파일 경로에서 액트 정보 추출.
- `_collect_dlgids(self, items, label, revision, acts, trigger)` (줄 146): dlgId 항목 수집 및 메타데이터 기록.
- `get(self, dlgId)` (줄 189): dlgId에 대한 메타데이터 조회.
- `get_stats(self)` (줄 200): 역참조 맵 통계.

## 함수

### `build_reference_map(narrative_path)`
- 위치: 줄 222
- 설명: 역참조 맵 빌드 헬퍼.

Args:
    narrative_path: eb_narrative/narrative 경로

Returns:
    빌드된 DialogueReferenceMap
