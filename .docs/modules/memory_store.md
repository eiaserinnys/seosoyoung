# memory/store.py

> 경로: `seosoyoung/memory/store.py`

## 개요

관찰 로그 저장소

파일 기반으로 세션(thread_ts) 단위 관찰 로그, 대화 로그, 장기 기억을 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {thread_ts}.json         # 세션별 관찰 로그 (JSON 항목 배열)
    │   ├── {thread_ts}.meta.json   # 메타데이터 (user_id 포함)
    │   └── {thread_ts}.inject      # OM 주입 플래그 (존재하면 다음 요청에 주입)
    ├── pending/
    │   └── {thread_ts}.jsonl       # 세션별 미관찰 대화 버퍼 (누적)
    ├── conversations/
    │   └── {thread_ts}.jsonl       # 세션별 대화 로그
    ├── candidates/
    │   └── {thread_ts}.jsonl       # 장기 기억 후보 (세션 단위 누적)
    └── persistent/
        ├── recent.json              # 활성 장기 기억 (JSON 항목 배열)
        ├── recent.meta.json        # 메타데이터
        └── archive/                # 컴팩션 시 이전 버전 보존
            └── recent_{timestamp}.json

## 클래스

### `ObservationItem`
- 위치: 줄 40
- 설명: 세션 관찰 항목

#### 메서드

- `to_dict(self)` (줄 50): 
- `from_dict(cls, d)` (줄 61): 

### `PersistentItem`
- 위치: 줄 73
- 설명: 장기 기억 항목

#### 메서드

- `to_dict(self)` (줄 82): 
- `from_dict(cls, d)` (줄 94): 

### `MemoryRecord`
- 위치: 줄 238
- 설명: 세션별 관찰 로그 레코드

thread_ts를 기본 키로 사용하고, user_id는 메타데이터로 보관합니다.

#### 메서드

- `to_meta_dict(self)` (줄 255): 메타데이터를 직렬화 가능한 dict로 변환
- `from_meta_dict(cls, data, observations)` (줄 274): dict에서 MemoryRecord를 복원

### `MemoryStore`
- 위치: 줄 300
- 설명: 파일 기반 관찰 로그 저장소

세션(thread_ts)을 기본 키로 사용합니다.

#### 메서드

- `__init__(self, base_dir)` (줄 306): 
- `_ensure_dirs(self)` (줄 314): 저장소 디렉토리가 없으면 생성
- `_obs_path(self, thread_ts)` (줄 322): 
- `_obs_md_path(self, thread_ts)` (줄 325): 레거시 .md 경로 (마이그레이션용)
- `_meta_path(self, thread_ts)` (줄 329): 
- `_lock_path(self, thread_ts)` (줄 332): 
- `_conv_path(self, thread_ts)` (줄 335): 
- `get_record(self, thread_ts)` (줄 338): 세션의 관찰 레코드를 로드합니다. 없으면 None.
- `save_record(self, record)` (줄 369): 관찰 레코드를 저장합니다.
- `_pending_path(self, thread_ts)` (줄 387): 
- `_pending_lock_path(self, thread_ts)` (줄 390): 
- `append_pending_messages(self, thread_ts, messages)` (줄 393): 미관찰 대화를 세션별 버퍼에 누적합니다.
- `load_pending_messages(self, thread_ts)` (줄 403): 미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트.
- `clear_pending_messages(self, thread_ts)` (줄 419): 관찰 완료 후 미관찰 대화 버퍼를 비웁니다.
- `_new_obs_path(self, thread_ts)` (줄 427): 
- `_new_obs_md_path(self, thread_ts)` (줄 430): 레거시 .new.md 경로 (마이그레이션용)
- `save_new_observations(self, thread_ts, content)` (줄 434): 이번 턴에서 새로 추가된 관찰만 별도 저장합니다.
- `get_new_observations(self, thread_ts)` (줄 442): 저장된 새 관찰을 반환합니다. 없으면 빈 리스트.
- `clear_new_observations(self, thread_ts)` (줄 456): 주입 완료된 새 관찰을 클리어합니다.
- `_inject_flag_path(self, thread_ts)` (줄 466): 
- `set_inject_flag(self, thread_ts)` (줄 469): 다음 요청에 OM을 주입하도록 플래그를 설정합니다.
- `check_and_clear_inject_flag(self, thread_ts)` (줄 474): inject 플래그를 확인하고 있으면 제거합니다.
- `save_conversation(self, thread_ts, messages)` (줄 486): 세션 대화 로그를 JSONL로 저장합니다.
- `load_conversation(self, thread_ts)` (줄 495): 세션 대화 로그를 로드합니다. 없으면 None.
- `_candidates_path(self, thread_ts)` (줄 511): 
- `_candidates_lock_path(self, thread_ts)` (줄 514): 
- `append_candidates(self, thread_ts, entries)` (줄 517): 후보 항목을 세션별 파일에 누적합니다.
- `load_candidates(self, thread_ts)` (줄 527): 세션별 후보를 로드합니다. 없으면 빈 리스트.
- `load_all_candidates(self)` (줄 543): 전체 세션의 후보를 수집합니다.
- `count_all_candidate_tokens(self)` (줄 557): 전체 후보의 content 필드 토큰 합산.
- `clear_all_candidates(self)` (줄 571): 모든 후보 파일을 삭제합니다.
- `_persistent_content_path(self)` (줄 583): 
- `_persistent_md_path(self)` (줄 586): 레거시 .md 경로 (마이그레이션용)
- `_persistent_meta_path(self)` (줄 590): 
- `_persistent_lock_path(self)` (줄 593): 
- `_persistent_archive_dir(self)` (줄 596): 
- `get_persistent(self)` (줄 599): 장기 기억을 로드합니다. 없으면 None.
- `save_persistent(self, content, meta)` (줄 633): 장기 기억을 저장합니다.
- `archive_persistent(self)` (줄 648): 기존 장기 기억을 archive/에 백업합니다.

## 함수

### `_next_seq(items, prefix, date_str)`
- 위치: 줄 107
- 설명: 기존 항목에서 같은 날짜의 최대 시퀀스 번호 + 1을 반환.

### `generate_obs_id(existing_items, date_str)`
- 위치: 줄 123
- 설명: 관찰 항목 ID를 생성합니다.

### `generate_ltm_id(existing_items, date_str)`
- 위치: 줄 132
- 설명: 장기 기억 항목 ID를 생성합니다.

### `parse_md_observations(md_text)`
- 위치: 줄 144
- 설명: 마크다운 관찰 로그를 항목 리스트로 파싱합니다.

## [YYYY-MM-DD] ... 헤더로 세션 날짜를 결정하고,
이모지(🔴🟡🟢)로 시작하는 줄을 항목으로 추출합니다.

### `parse_md_persistent(md_text)`
- 위치: 줄 192
- 설명: 마크다운 장기 기억을 항목 리스트로 파싱합니다.
