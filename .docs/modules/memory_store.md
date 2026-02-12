# memory/store.py

> 경로: `seosoyoung/memory/store.py`

## 개요

관찰 로그 저장소

파일 기반으로 세션(thread_ts) 단위 관찰 로그, 대화 로그, 장기 기억을 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {thread_ts}.md          # 세션별 관찰 로그 (마크다운)
    │   ├── {thread_ts}.meta.json   # 메타데이터 (user_id 포함)
    │   └── {thread_ts}.inject      # OM 주입 플래그 (존재하면 다음 요청에 주입)
    ├── pending/
    │   └── {thread_ts}.jsonl       # 세션별 미관찰 대화 버퍼 (누적)
    ├── conversations/
    │   └── {thread_ts}.jsonl       # 세션별 대화 로그
    ├── candidates/
    │   └── {thread_ts}.jsonl       # 장기 기억 후보 (세션 단위 누적)
    └── persistent/
        ├── recent.md               # 활성 장기 기억
        ├── recent.meta.json        # 메타데이터
        └── archive/                # 컴팩션 시 이전 버전 보존
            └── recent_{timestamp}.md

## 클래스

### `MemoryRecord`
- 위치: 줄 36
- 설명: 세션별 관찰 로그 레코드

thread_ts를 기본 키로 사용하고, user_id는 메타데이터로 보관합니다.

#### 메서드

- `to_meta_dict(self)` (줄 52): 메타데이터를 직렬화 가능한 dict로 변환
- `from_meta_dict(cls, data, observations)` (줄 68): dict에서 MemoryRecord를 복원

### `MemoryStore`
- 위치: 줄 91
- 설명: 파일 기반 관찰 로그 저장소

세션(thread_ts)을 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 97): 
- `_ensure_dirs(self)` (줄 105): 저장소 디렉토리가 없으면 생성
- `_obs_path(self, thread_ts)` (줄 113): 
- `_meta_path(self, thread_ts)` (줄 116): 
- `_lock_path(self, thread_ts)` (줄 119): 
- `_conv_path(self, thread_ts)` (줄 122): 
- `get_record(self, thread_ts)` (줄 125): 세션의 관찰 레코드를 로드합니다. 없으면 None.
- `save_record(self, record)` (줄 142): 관찰 레코드를 저장합니다.
- `_pending_path(self, thread_ts)` (줄 159): 
- `_pending_lock_path(self, thread_ts)` (줄 162): 
- `append_pending_messages(self, thread_ts, messages)` (줄 165): 미관찰 대화를 세션별 버퍼에 누적합니다.
- `load_pending_messages(self, thread_ts)` (줄 175): 미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트.
- `clear_pending_messages(self, thread_ts)` (줄 191): 관찰 완료 후 미관찰 대화 버퍼를 비웁니다.
- `_inject_flag_path(self, thread_ts)` (줄 199): 
- `set_inject_flag(self, thread_ts)` (줄 202): 다음 요청에 OM을 주입하도록 플래그를 설정합니다.
- `check_and_clear_inject_flag(self, thread_ts)` (줄 207): inject 플래그를 확인하고 있으면 제거합니다.
- `save_conversation(self, thread_ts, messages)` (줄 219): 세션 대화 로그를 JSONL로 저장합니다.
- `load_conversation(self, thread_ts)` (줄 228): 세션 대화 로그를 로드합니다. 없으면 None.
- `_candidates_path(self, thread_ts)` (줄 244): 
- `_candidates_lock_path(self, thread_ts)` (줄 247): 
- `append_candidates(self, thread_ts, entries)` (줄 250): 후보 항목을 세션별 파일에 누적합니다.
- `load_candidates(self, thread_ts)` (줄 260): 세션별 후보를 로드합니다. 없으면 빈 리스트.
- `load_all_candidates(self)` (줄 276): 전체 세션의 후보를 수집합니다.
- `count_all_candidate_tokens(self)` (줄 290): 전체 후보의 content 필드 토큰 합산.
- `clear_all_candidates(self)` (줄 304): 모든 후보 파일을 삭제합니다.
- `_persistent_content_path(self)` (줄 316): 
- `_persistent_meta_path(self)` (줄 319): 
- `_persistent_lock_path(self)` (줄 322): 
- `_persistent_archive_dir(self)` (줄 325): 
- `get_persistent(self)` (줄 328): 장기 기억을 로드합니다. 없으면 None.
- `save_persistent(self, content, meta)` (줄 347): 장기 기억을 저장합니다.
- `_delivered_flag_path(self, thread_ts)` (줄 359): 
- `get_latest_undelivered_observation(self, exclude_thread_ts)` (줄 362): 미전달된 가장 최근 관찰 레코드를 반환하고 delivered 플래그를 설정합니다.
- `archive_persistent(self)` (줄 424): 기존 장기 기억을 archive/에 백업합니다.
