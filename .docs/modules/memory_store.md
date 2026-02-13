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

- `to_meta_dict(self)` (줄 53): 메타데이터를 직렬화 가능한 dict로 변환
- `from_meta_dict(cls, data, observations)` (줄 72): dict에서 MemoryRecord를 복원

### `MemoryStore`
- 위치: 줄 96
- 설명: 파일 기반 관찰 로그 저장소

세션(thread_ts)을 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 102): 
- `_ensure_dirs(self)` (줄 110): 저장소 디렉토리가 없으면 생성
- `_obs_path(self, thread_ts)` (줄 118): 
- `_meta_path(self, thread_ts)` (줄 121): 
- `_lock_path(self, thread_ts)` (줄 124): 
- `_conv_path(self, thread_ts)` (줄 127): 
- `get_record(self, thread_ts)` (줄 130): 세션의 관찰 레코드를 로드합니다. 없으면 None.
- `save_record(self, record)` (줄 147): 관찰 레코드를 저장합니다.
- `_pending_path(self, thread_ts)` (줄 164): 
- `_pending_lock_path(self, thread_ts)` (줄 167): 
- `append_pending_messages(self, thread_ts, messages)` (줄 170): 미관찰 대화를 세션별 버퍼에 누적합니다.
- `load_pending_messages(self, thread_ts)` (줄 180): 미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트.
- `clear_pending_messages(self, thread_ts)` (줄 196): 관찰 완료 후 미관찰 대화 버퍼를 비웁니다.
- `_new_obs_path(self, thread_ts)` (줄 204): 
- `save_new_observations(self, thread_ts, content)` (줄 207): 이번 턴에서 새로 추가된 관찰만 별도 저장합니다.
- `get_new_observations(self, thread_ts)` (줄 212): 저장된 새 관찰을 반환합니다. 없으면 빈 문자열.
- `clear_new_observations(self, thread_ts)` (줄 219): 주입 완료된 새 관찰을 클리어합니다.
- `_inject_flag_path(self, thread_ts)` (줄 225): 
- `set_inject_flag(self, thread_ts)` (줄 228): 다음 요청에 OM을 주입하도록 플래그를 설정합니다.
- `check_and_clear_inject_flag(self, thread_ts)` (줄 233): inject 플래그를 확인하고 있으면 제거합니다.
- `save_conversation(self, thread_ts, messages)` (줄 245): 세션 대화 로그를 JSONL로 저장합니다.
- `load_conversation(self, thread_ts)` (줄 254): 세션 대화 로그를 로드합니다. 없으면 None.
- `_candidates_path(self, thread_ts)` (줄 270): 
- `_candidates_lock_path(self, thread_ts)` (줄 273): 
- `append_candidates(self, thread_ts, entries)` (줄 276): 후보 항목을 세션별 파일에 누적합니다.
- `load_candidates(self, thread_ts)` (줄 286): 세션별 후보를 로드합니다. 없으면 빈 리스트.
- `load_all_candidates(self)` (줄 302): 전체 세션의 후보를 수집합니다.
- `count_all_candidate_tokens(self)` (줄 316): 전체 후보의 content 필드 토큰 합산.
- `clear_all_candidates(self)` (줄 330): 모든 후보 파일을 삭제합니다.
- `_persistent_content_path(self)` (줄 342): 
- `_persistent_meta_path(self)` (줄 345): 
- `_persistent_lock_path(self)` (줄 348): 
- `_persistent_archive_dir(self)` (줄 351): 
- `get_persistent(self)` (줄 354): 장기 기억을 로드합니다. 없으면 None.
- `save_persistent(self, content, meta)` (줄 373): 장기 기억을 저장합니다.
- `archive_persistent(self)` (줄 385): 기존 장기 기억을 archive/에 백업합니다.
