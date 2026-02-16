# search/git_watcher.py

> 경로: `seosoyoung/search/git_watcher.py`

## 개요

Git Poll Watcher — eb_narrative/eb_lore HEAD 감시 + 인덱스 자동 재빌드.

백그라운드 스레드에서 git refs를 주기적으로 폴링하여 원격 변경을 감지하고,
변경 시 git pull → 인덱스 재빌드를 수행한다.

핵심 설계:
- swap-on-complete: 재빌드 중에도 기존 인덱스로 검색 서비스 유지
- lock 파일: pre-commit hook(.tools/build-dialogue-index)과 동시 빌드 방지
- 재빌드 실패 시 기존 인덱스 유지 + 에러 로깅

## 클래스

### `BuildLock`
- 위치: 줄 26
- 설명: 파일 기반 빌드 lock — pre-commit hook과 동시 빌드 방지.

#### 메서드

- `__init__(self, lock_path)` (줄 29): 
- `acquire(self, owner, timeout)` (줄 32): lock 획득 시도. timeout 내 획득 못 하면 False.
- `release(self)` (줄 56): lock 해제.
- `is_locked(self)` (줄 61): 

### `IndexStatus`
- 위치: 줄 65
- 설명: 인덱스 상태 정보 — lore_index_status 도구에서 조회.

#### 메서드

- `__init__(self)` (줄 68): 
- `to_dict(self)` (줄 78): 

### `GitWatcher`
- 위치: 줄 128
- 설명: Git HEAD 폴링 워처 — 백그라운드 스레드로 실행.

Args:
    narrative_path: eb_narrative 리포 경로
    lore_path: eb_lore 리포 경로
    index_root: 인덱스 루트 디렉토리
    poll_interval: 폴링 간격 (초, 기본 60)
    on_rebuild: 재빌드 완료 콜백 (인덱스 핫 리로드용)

#### 메서드

- `__init__(self, narrative_path, lore_path, index_root, poll_interval, on_rebuild)` (줄 139): 
- `start(self)` (줄 163): 워처 백그라운드 스레드 시작.
- `stop(self, timeout)` (줄 190): 워처 정지.
- `is_running(self)` (줄 199): 
- `_poll_loop(self)` (줄 202): 메인 폴링 루프.
- `_poll_once(self)` (줄 214): 한 번의 폴링 사이클.
- `_rebuild_index(self)` (줄 259): 인덱스 재빌드 (swap-on-complete 전략).
- `_swap_indices(self, tmp_root)` (줄 308): 임시 빌드 결과물을 실제 인덱스 위치로 교체.
- `_cleanup_tmp(self)` (줄 341): 재빌드 실패 시 임시 디렉토리 정리.

## 함수

### `_read_git_head(repo_path)`
- 위치: 줄 91
- 설명: git rev-parse HEAD로 현재 HEAD 해시를 읽는다.

### `_git_pull(repo_path)`
- 위치: 줄 108
- 설명: git pull을 수행한다. 성공 시 True.
